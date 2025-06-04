import sys, os, re, json
import openai
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox,
    QTreeWidgetItem, QDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QVBoxLayout, QTreeWidget, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush
from ui_main import Ui_MainWindow
import file_loader
import dat_decrypt
import asset_extractor

# ───────────────────────────────────────────────────────────────
# Парсер тегов / плейсхолдеров
TAG_REGEX = re.compile(r'(<[^>]+>|%\w+|\{[0-9]+\}|\\n|#\w+:)', re.IGNORECASE)
def extract_tokens(text: str) -> list[str]:
    return TAG_REGEX.findall(text or "")

# Статус сцены
COLOR_MAP = {"empty": "#FFCCCC", "partial": "#FFF4CC", "done": "#CCFFCC"}
def scene_status(df_slice) -> str:
    ru = df_slice["RussianTranslation"].astype(str)
    if (ru == "").all(): return "empty"
    if (ru != "").all(): return "done"
    return "partial"

# OpenAI клиент (читает OPENAI_API_KEY из окружения)
client = openai.OpenAI(
    api_key=os.getenv('OPENAI_API_KEY')
)

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        # Данные
        self.df = None
        self.current_path = ""
        # Поиск
        self.flat_items: list[QTreeWidgetItem] = []
        self.search_pattern = ""
        self.search_idx = -1
        # Глоссарий
        self.glossary: dict[str,str] = {}

        # Сигналы
        self.ui.btnOpen.clicked.connect(self.open_csv)
        self.ui.btnSave.clicked.connect(self.save_csv)
        self.ui.btnStats.clicked.connect(self.show_stats)
        self.ui.btnAutoTranslate.clicked.connect(self.auto_translate_scene)
        self.ui.tree.itemChanged.connect(self.mark_edited)
        self.ui.chkHideDone.stateChanged.connect(self.populate_tree)
        self.ui.btnFind.clicked.connect(self.search_next)
        self.ui.txtSearch.returnPressed.connect(self.search_next)

        self.ui.btnOpenDat.clicked.connect(self.open_dat)
        self.ui.btnExportAllAssets.clicked.connect(self.export_all_assets)
        self.ui.btnExportAsset.clicked.connect(self.export_selected_asset)

        # Глоссарий UI
        self.ui.btnImportGlossary.clicked.connect(self.import_glossary)
        self.ui.btnExportGlossary.clicked.connect(self.export_glossary)
        self.ui.btnAddTerm.clicked.connect(self.add_glossary_term)
        self.ui.btnRemoveTerm.clicked.connect(self.remove_glossary_term)
        self.ui.btnApplyGlossary.clicked.connect(self.apply_glossary)

        # Загрузка и отображение глоссария
        self.load_glossary()
        self.populate_glossary()

    # Открыть CSV
    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть CSV", "", "CSV files (*.csv)")
        if not path:
            return
        try:
            self.df = file_loader.load_csv(path)
            # Проверка столбцов
            for col in ["File","StepID","Character","EnglishText"]:
                if col not in self.df.columns:
                    raise KeyError(f"Отсутствует колонка {col}")
            if "RussianTranslation" not in self.df.columns:
                self.df["RussianTranslation"] = ""
        except Exception as e:
            QMessageBox.critical(self, "Ошибка чтения", str(e))
            return
        self.current_path = path
        self.populate_tree()

    # Заполнить дерево
    def populate_tree(self):
        if self.df is None: return
        tree = self.ui.tree
        tree.blockSignals(True)
        tree.clear()

        headers = ["File","StepID","Character","EnglishText","RussianTranslation"]
        tree.setColumnCount(len(headers))
        tree.setHeaderLabels(headers)

        hide_done = self.ui.chkHideDone.isChecked()
        self.flat_items.clear()

        for file_name, group in self.df.groupby("File", sort=False):
            status = scene_status(group)
            if hide_done and status == "done":
                continue
            # Корневой узел сцены
            root = QTreeWidgetItem(tree)
            root.setText(0, file_name)
            root.setFirstColumnSpanned(True)
            root.setExpanded(False)
            root.setBackground(0, QBrush(QColor(COLOR_MAP[status])))

            # Дочерние реплики
            for idx, rec in group.iterrows():
                child = QTreeWidgetItem(root)
                child.setText(1, str(rec["StepID"]))
                child.setText(2, rec["Character"])
                child.setText(3, rec["EnglishText"])
                child.setText(4, rec["RussianTranslation"])
                child.setFlags(child.flags() | Qt.ItemFlag.ItemIsEditable)
                # Подсветка тегов
                if extract_tokens(rec["EnglishText"]):
                    hl = QBrush(QColor("#FFFACD"))
                    child.setBackground(3, hl)
                    child.setBackground(4, hl)
                self.flat_items.append(child)

        tree.blockSignals(False)
        tree.expandToDepth(0)
        self.search_idx = -1

    # Обработка правок
    def mark_edited(self, item, column):
        if item.parent() is None:
            return
        file_name = item.parent().text(0)
        step_id = item.text(1)
        mask = (self.df["File"] == file_name) & (self.df["StepID"].astype(str) == step_id)

        # Откат изменения негружаемых колонок
        if column != 4:
            orig_cols = ["StepID", "Character", "EnglishText"]
            value = self.df.loc[mask, orig_cols[column-1]].values[0]
            item.setText(column, str(value))
            return

        # Проверка тегов
        orig = item.text(3)
        new = item.text(4)
        if extract_tokens(orig) != extract_tokens(new):
            QMessageBox.warning(self, "Ошибка", "Теги не совпадают: " + " ".join(extract_tokens(orig)))
            item.setText(4, self.df.loc[mask, "RussianTranslation"].values[0])
            return

        # Сохранение перевода
        self.df.loc[mask, "RussianTranslation"] = new
        # Обновление цвета сцены
        parent = item.parent()
        status = scene_status(self.df[self.df["File"] == file_name])
        parent.setBackground(0, QBrush(QColor(COLOR_MAP[status])))
        if status == "done" and self.ui.chkHideDone.isChecked():
            parent.setHidden(True)

    # Авто-перевод сцены через OpenAI
    def auto_translate_scene(self):
        sel = self.ui.tree.currentItem()
        if sel is None:
            QMessageBox.information(self, "Авто-перевод", "Выберите сцену или строку.")
            return
        root = sel.parent() if sel.parent() else sel
        file_name = root.text(0)
        group = self.df[self.df["File"] == file_name]
        if group.empty:
            QMessageBox.information(self, "Авто-перевод", "Нет строк для перевода.")
            return
        lines = group["EnglishText"].tolist()
        prompt = "Переведи на русский, сохрани теги. Построчно:\n" + "\n".join(lines)
        try:
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            out = resp.choices[0].message.content.strip().splitlines()
            if len(out) != len(lines):
                QMessageBox.warning(self, "Авто-перевод", "Неверное число строк.")
                return
            for i, (idx, _) in enumerate(group.iterrows()):
                self.df.at[idx, "RussianTranslation"] = out[i]
                child = root.child(i)
                child.setText(4, out[i])
            status = scene_status(group)
            root.setBackground(0, QBrush(QColor(COLOR_MAP[status])))
        except Exception as e:
            QMessageBox.critical(self, "Авто-перевод", str(e))

    # Поиск по репликам
    def search_next(self):
        pattern = self.ui.txtSearch.text().strip().lower()
        if not pattern:
            return
        if pattern != self.search_pattern:
            self.search_pattern = pattern
            self.search_idx = -1
        total = len(self.flat_items)
        if total == 0:
            QMessageBox.information(self, "Поиск", "Нет данных.")
            return
        start = (self.search_idx + 1) % total
        idx = start
        while True:
            item = self.flat_items[idx]
            if pattern in (item.text(3) + " " + item.text(4)).lower():
                self.search_idx = idx
                item.parent().setExpanded(True)
                self.ui.tree.setCurrentItem(item)
                self.ui.tree.scrollToItem(item)
                return
            idx = (idx + 1) % total
            if idx == start:
                break
        QMessageBox.information(self, "Поиск", "Совпадений нет.")

    # Загрузка/сохранение глоссария
    def load_glossary(self):
        try:
            with open('glossary.json', 'r', encoding='utf-8') as f:
                self.glossary = json.load(f)
        except FileNotFoundError:
            self.glossary = {}
    def save_glossary(self):
        with open('glossary.json', 'w', encoding='utf-8') as f:
            json.dump(self.glossary, f, ensure_ascii=False, indent=2)

    # Отобразить глоссарий в таблице
    def populate_glossary(self):
        table = self.ui.tableGlossary

        # Настраиваем колонки и заголовки
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Term", "Translation"])

        # Очищаем содержимое и выставляем нужное число строк
        table.clearContents()
        table.setRowCount(len(self.glossary))

        # Заполняем из словаря
        for r, (term, trans) in enumerate(self.glossary.items()):
            table.setItem(r, 0, QTableWidgetItem(term))
            table.setItem(r, 1, QTableWidgetItem(trans))

        # Немного подстроим ширину
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )

    def import_glossary(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт глоссария", "", "JSON (*.json)")
        if path:
            with open(path, encoding='utf-8') as f:
                self.glossary = json.load(f)
            self.save_glossary()
            self.populate_glossary()

    def export_glossary(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт глоссария", "glossary.json", "JSON (*.json)")
        if path:
            self.save_glossary()
            QMessageBox.information(self, "Глоссарий", "Экспорт выполнен.")

    def add_glossary_term(self):
        table = self.ui.tableGlossary
        r = table.rowCount()
        table.insertRow(r)

    def remove_glossary_term(self):
        table = self.ui.tableGlossary
        r = table.currentRow()
        if r >= 0:
            table.removeRow(r)
            # Обновляем словарь
            self.glossary = {table.item(i,0).text(): table.item(i,1).text()
                              for i in range(table.rowCount())}
            self.save_glossary()

    def apply_glossary(self):
        for term, trans in self.glossary.items():
            for idx, rec in self.df.iterrows():
                if term in rec['EnglishText']:
                    orig_ru = rec['RussianTranslation'] or rec['EnglishText']
                    new_ru = orig_ru.replace(term, trans)
                    self.df.at[idx, 'RussianTranslation'] = new_ru
        self.populate_tree()
        QMessageBox.information(self, "Глоссарий", "Подстановка выполнена.")

    # Статистика
    def show_stats(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Статистика перевода")
        table = QTableWidget(dlg)
        scenes = sorted(self.df["File"].unique())
        table.setRowCount(len(scenes) + 1)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Сцена","Строк","Переведено","%","Символов RU"])
        tot_r = tot_d = tot_c = 0
        for r, f in enumerate(scenes):
            sub = self.df[self.df["File"]==f]
            rows = len(sub)
            done = (sub["RussianTranslation"]!="").sum()
            perc = 0 if rows==0 else round(done/rows*100)
            chars = sub["RussianTranslation"].str.len().sum()
            tot_r+=rows; tot_d+=done; tot_c+=chars
            for c, val in enumerate([f,str(rows),str(done),f"{perc}%",str(chars)]):
                table.setItem(r,c,QTableWidgetItem(val))
        perc_all = 0 if tot_r==0 else round(tot_d/tot_r*100)
        footer = ['Итого', str(tot_r), str(tot_d), f'{perc_all}%', str(tot_c)]
        for c, val in enumerate(footer):
            item = QTableWidgetItem(val)
            item.setBackground(QColor("#E8E8E8"))
            table.setItem(len(scenes), c, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        lay = QVBoxLayout(); lay.addWidget(table)
        dlg.setLayout(lay); dlg.resize(600,400); dlg.exec()

    # Сохранить CSV
    def save_csv(self):
        if self.df is None:
            QMessageBox.information(self, "Сохранение", "Откройте CSV.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить CSV", self.current_path, "CSV files (*.csv)")
        if path:
            file_loader.save_csv(self.df, path)
            QMessageBox.information(self, "Готово", "Сохранено.")

    def open_dat(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть .dat", "", "DAT files (*.dat)")
        if not path: return

        base, ext = os.path.splitext(path)
        dec = base + "_DEC" + ext
        if not dat_decrypt.decrypt_dat(path, dec):
            QMessageBox.critical(self, ".dat → DEC", "Не удалось найти ключ дешифрования.")
            return

        # Готовим модель
        assets = asset_extractor.list_assets(dec)

        # Создаём диалог ПО КОДУ, с деревом и двумя своими кнопками
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Ассеты: {os.path.basename(dec)}")
        vlay = QVBoxLayout(dlg)

        tree = QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderLabels(["Type", "Name"])
        for typ, name in assets:
            it = QTreeWidgetItem(tree)
            it.setText(0, typ)
            it.setText(1, name)
        vlay.addWidget(tree)

        # Панель кнопок -------------
        hl = QHBoxLayout()
        btnAll = QPushButton("Экспорт всего")
        btnSel = QPushButton("Экспорт выбранного")
        hl.addWidget(btnAll)
        hl.addWidget(btnSel)
        vlay.addLayout(hl)

        # Логика кнопок -------------
        def _export_all():
            out = QFileDialog.getExistingDirectory(dlg, "Папка для экспорта всех")
            if out:
                asset_extractor.extract_all(dec, out)
                QMessageBox.information(dlg, "Экспорт", f"Все ассеты в {out}")

        def _export_sel():
            idx = tree.currentIndex().row()
            if idx < 0:
                QMessageBox.information(dlg, "Экспорт", "Ничего не выбрано.")
                return
            out = QFileDialog.getExistingDirectory(dlg, "Папка для экспорта")
            if out:
                asset_extractor.extract_asset(dec, idx, out)
                QMessageBox.information(dlg, "Экспорт", f"Ассет экспортирован в {out}")

        btnAll.clicked.connect(_export_all)
        btnSel.clicked.connect(_export_sel)

        # Показываем модально, но кнопки внутри работают
        dlg.exec()

    def export_all_assets(self):
        # bundle_path храните в атрибуте после decrypt_dat, например self.last_dec_path
        if not hasattr(self, 'last_dec_path'):
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для экспорта всех ассетов")
        if not out_dir:
            return
        asset_extractor.extract_all(self.last_dec_path, out_dir)
        QMessageBox.information(self, "Экспорт", f"Все ассеты экспортированы в:\n{out_dir}")

    def export_selected_asset(self):
        if not hasattr(self, 'last_dec_path'):
            return
        it = self.ui.tree.currentItem()
        if it is None or it.parent() is None:
            QMessageBox.information(self, "Экспорт", "Выберите ассет в списке.")
            return
        # определяем индекс объекта по порядку в asset_extractor.list_assets
        idx = self.ui.tree.indexOfTopLevelItem(it)  # или сохраните flat list при открытии
        out_dir = QFileDialog.getExistingDirectory(self, "Папка для экспорта ассета")
        if not out_dir:
            return
        asset_extractor.extract_asset(self.last_dec_path, idx, out_dir)
        QMessageBox.information(self, "Экспорт", f"Ассет экспортирован в:\n{out_dir}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainApp()
    w.show()
    sys.exit(app.exec())
