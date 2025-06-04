import pandas as pd

def load_csv(path: str) -> pd.DataFrame:
    """Считывает CSV в DataFrame, пустые ячейки не превращает в NaN."""
    return pd.read_csv(path, keep_default_na=False, encoding="utf-8")

def save_csv(df: pd.DataFrame, path: str) -> None:
    """Сохраняет DataFrame без индекса."""
    df.to_csv(path, index=False, encoding="utf-8")
