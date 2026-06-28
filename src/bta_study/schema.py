"""
Контракт данных (Pandera). Падает с понятной ошибкой, ЕСЛИ аналитическая
таблица нарушает ожидания — до того, как кривые данные попадут в статистику.

Это замена ручному «вижу артефакт -> правлю»: артефакт ловится автоматически
на границе слоёв.
"""
from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Column, Check, DataFrameSchema

analytical_schema = DataFrameSchema(
    {
        "bta_date": Column("datetime64[ns]", nullable=False,
                           checks=Check.in_range(pd.Timestamp("2024-01-01"),
                                                  pd.Timestamp("2027-01-01"))),
        "age": Column(float, nullable=True,
                      checks=Check.in_range(18, 100)),  # критерий включения 18+
        "sex": Column(str, nullable=True, checks=Check.isin(["м", "ж"])),
        "drainage": Column(str, checks=Check.isin(
            ["intermittent", "indwelling", "cystostomy", "pads", "unknown"])),
        "proph_regimen": Column(str, checks=Check.isin(
            ["none", "single", "prolonged", "combined"])),
        "max_log_cfu": Column(float, nullable=True,
                              checks=Check.in_range(0, 9)),
        "oam_to_bta_days": Column(float, nullable=True),
        "mi_to_bta_days": Column(float, nullable=True),
        "uti_5d": Column(object, nullable=True),     # True/False/None
        "censored": Column(bool),
    },
    strict=False,      # допускаем дополнительные служебные колонки
    coerce=True,
)


def validate(df: pd.DataFrame) -> pd.DataFrame:
    """Прогоняет df через контракт. Бросает SchemaError при нарушении."""
    work = df.copy()
    # приведение типов под контракт
    work["bta_date"] = pd.to_datetime(work["bta_date"], errors="coerce")
    work["age"] = pd.to_numeric(work["age"], errors="coerce")
    for c in ("oam_to_bta_days", "mi_to_bta_days", "max_log_cfu"):
        work[c] = pd.to_numeric(work[c], errors="coerce")
    return analytical_schema.validate(work, lazy=True)
