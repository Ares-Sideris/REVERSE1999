import UnityPy
import os
from PIL import Image  # UnityPy отдаёт pillow-объект для текстур

# ------------------------------------------------------------------
# Получение списка ассетов из Unity AssetBundle (.dat)
# ------------------------------------------------------------------
def list_assets(bundle_path: str) -> list[tuple[int, str, str]]:
    """
    Возвращает список кортежей (index, тип_ассета, имя_ассета)
    из Unity AssetBundle.
    index — порядковый номер объекта в env.objects.
    """
    env = UnityPy.load(bundle_path)
    assets = []
    for idx, obj in enumerate(env.objects):
        try:
            container = obj.read()
            name = getattr(container, 'name', None) or getattr(container, 'original_path', None)
            if not name:
                name = f"path_id_{obj.path_id}"
            typ = container.__class__.__name__
            assets.append((idx, typ, name))
        except Exception:
            continue
    return assets

# ------------------------------------------------------------------
# Экспорт всех ассетов
# ------------------------------------------------------------------
def extract_all(bundle_path: str, output_dir: str) -> int:
    """
    Экспортирует все ассеты из AssetBundle в указанную папку.
    Возвращает количество успешно экспортированных файлов.
    """
    env = UnityPy.load(bundle_path)
    os.makedirs(output_dir, exist_ok=True)
    count = 0
    for idx, obj in enumerate(env.objects):
        try:
            container = obj.read()
            name = getattr(container, 'name', None) or getattr(container, 'original_path', None)
            if not name:
                name = f"path_id_{obj.path_id}"

            # Texture2D → PNG
            if container.type.name == "Texture2D":
                img = container.image
                out_path = os.path.join(output_dir, f"{name}.png")
                img.save(out_path)
                count += 1
            # AudioClip → WAV
            elif container.type.name == "AudioClip":
                data = container.read()
                out_path = os.path.join(output_dir, f"{name}.wav")
                with open(out_path, "wb") as f:
                    f.write(data)
                count += 1
            # Всё остальное → .bytes
            else:
                data = container.read()
                if isinstance(data, (bytes, bytearray)) and data:
                    out_path = os.path.join(output_dir, f"{name}.bytes")
                    with open(out_path, "wb") as f:
                        f.write(data)
                    count += 1
        except Exception:
            continue
    return count

# ------------------------------------------------------------------
# Экспорт одного ассета
# ------------------------------------------------------------------
def extract_asset(bundle_path: str, asset_index: int, output_dir: str) -> bool:
    """
    Экспорт одного ассета по его индексу asset_index в output_dir.
    Возвращает True, если файл успешно записан.
    """
    env = UnityPy.load(bundle_path)
    if asset_index < 0 or asset_index >= len(env.objects):
        return False
    os.makedirs(output_dir, exist_ok=True)
    try:
        obj = env.objects[asset_index]
        container = obj.read()
        name = getattr(container, 'name', None) or getattr(container, 'original_path', None)
        if not name:
            name = f"path_id_{obj.path_id}"

        # Texture2D → PNG
        if container.type.name == "Texture2D":
            img = container.image
            out_path = os.path.join(output_dir, f"{name}.png")
            img.save(out_path)
        # AudioClip → WAV
        elif container.type.name == "AudioClip":
            data = container.read()
            out_path = os.path.join(output_dir, f"{name}.wav")
            with open(out_path, "wb") as f:
                f.write(data)
        # Всё остальное → .bytes
        else:
            data = container.read()
            if isinstance(data, (bytes, bytearray)) and data:
                out_path = os.path.join(output_dir, f"{name}.bytes")
                with open(out_path, "wb") as f:
                    f.write(data)
        return True
    except Exception:
        return False
