"""
Дедупликация процедур. Единица анализа — ПРОЦЕДУРА, ключ — (фамилия, дата БТА).

Это та самая точка, где в реальном чате возникло расхождение 64 vs 66:
разные ключи дедупликации дают разное число эпизодов. Поэтому ключ объявлен
явно и зафиксирован в протоколе, а не выбирается по ходу.
"""
from __future__ import annotations

import re

import pandas as pd


def _last_name(name_cell: str) -> str:
    if not isinstance(name_cell, str):
        return ""
    # первое слово в верхнем регистре — фамилия
    m = re.match(r"\s*([А-ЯЁA-Z\-]{2,})", name_cell)
    return m.group(1).upper() if m else ""


def deduplicate(df: pd.DataFrame, bta_date_col: str = "bta_date") -> pd.DataFrame:
    """
    df должен уже содержать распарсенную дату БТА (bta_date_col, тип date).
    Возвращает копию без межтабличных дубликатов; добавляет колонки
    last_name и procedure_key для прозрачности.
    """
    out = df.copy()
    out["last_name"] = out["name_cell"].map(_last_name)
    out["procedure_key"] = (
        out["last_name"] + "|" + out[bta_date_col].astype(str)
    )
    before = len(out)
    # при дублях оставляем запись с максимумом непустых полей (богаче информация)
    out["_nonnull"] = out.notna().sum(axis=1)
    out = (
        out.sort_values("_nonnull", ascending=False)
        .drop_duplicates(subset="procedure_key", keep="first")
        .drop(columns="_nonnull")
        .sort_values("procedure_key")
        .reset_index(drop=True)
    )
    out.attrs["n_removed_duplicates"] = before - len(out)
    return out
