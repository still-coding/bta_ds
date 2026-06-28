"""
Слой ingestion: читает обе исходные «таблицы» и собирает единый длинный
DataFrame сырых записей. Никакой статистики здесь нет — только чтение и
приведение имён столбцов. Один вход -> один предсказуемый выход (идемпотентно).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# каноничные внутренние имена столбцов
RENAME = {
    "№": "row_no",
    "Фамилия И.О.": "name_cell",
    "Дата БТА": "bta_date_raw",
    "пол": "sex",
    "возраст": "age_raw",
    "а/б профилактика": "prophylaxis_text",
    "бактериурия": "micro_text",
    "№ анализа": "oam_lab_no",
    "ИМВП в теч. 5 дней после БТА (Да-дата/нет)": "uti_5d_text",
    "Посев после БТА (да-дата/нет)": "post_culture_text",
    "Номер анализа": "post_lab_no",
    "м/о": "organism_col",
    "Другое": "other_text",
}


def load_raw(raw_dir: Path) -> pd.DataFrame:
    frames = []
    for path in sorted(Path(raw_dir).glob("raw_*.xlsx")):
        df = pd.read_excel(path, dtype={"Дата БТА": object})
        df = df.rename(columns=RENAME)
        df["source_file"] = path.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"Не найдено raw_*.xlsx в {raw_dir}")
    out = pd.concat(frames, ignore_index=True)
    return out
