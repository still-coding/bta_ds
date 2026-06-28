"""
Feature engineering. Превращает сырые строки в аналитическую таблицу:
распарсенные даты/возраст/микробиология + вычисляемые интервалы и конечные
точки. Все колонки — детерминированные функции от входа.
"""
from __future__ import annotations

import pandas as pd

from . import parsers as P


def build_features(raw: pd.DataFrame) -> pd.DataFrame:
    """raw — выход ingest.load_raw(). Возвращает аналитическую таблицу процедур."""
    rows = []
    for _, r in raw.iterrows():
        bta = P.fix_year_typo(P.parse_date(r["bta_date_raw"]))
        age, age_src = P.resolve_age(r.get("age_raw"), r.get("name_cell"), bta)
        proph = P.classify_prophylaxis(r.get("prophylaxis_text", ""),
                                       r.get("micro_text", ""))
        micro = P.parse_microbiology(r.get("micro_text", ""))
        outcome = P.parse_uti_outcome(r.get("uti_5d_text", ""))
        distant, distant_date = P.parse_distant_uti(r.get("other_text", ""))

        # интервалы (сут): положительное значение = тест выполнен ДО БТА
        oam_to_bta = (bta - micro.oam_date).days if (bta and micro.oam_date) else None
        mi_to_bta = (bta - micro.mi_date).days if (bta and micro.mi_date) else None
        oam_mi_gap = (abs((micro.oam_date - micro.mi_date).days)
                      if (micro.oam_date and micro.mi_date) else None)

        rows.append({
            "source_file": r.get("source_file"),
            "name_cell": r.get("name_cell"),
            "bta_date": bta,
            "sex": str(r.get("sex", "")).strip().lower() or None,
            "age": age,
            "age_source": age_src,
            "drainage": P.parse_drainage(r.get("name_cell", "")),
            # профилактика
            "proph_regimen": proph.regimen,
            "proph_drug": proph.drug,
            "resistant_noted": proph.resistant_noted,
            # скрининг
            "oam_done": micro.oam_positive is not None,
            "oam_positive": micro.oam_positive,
            "oam_date": micro.oam_date,
            "mi_done": micro.mi_done,
            "mi_positive": micro.mi_positive if micro.mi_done else None,
            "mi_date": micro.mi_date,
            "max_log_cfu": micro.max_log_cfu,
            "organisms": ";".join(o.name for o in micro.organisms) or None,
            "n_organisms": len(micro.organisms),
            # интервалы
            "oam_to_bta_days": oam_to_bta,
            "mi_to_bta_days": mi_to_bta,
            "oam_mi_gap_days": oam_mi_gap,
            # конечные точки
            "uti_5d": outcome.uti_5d,
            "censored": outcome.censored,
            "distant_uti": distant,
        })

    df = pd.DataFrame(rows)

    # производные флаги для удобства анализа
    df["significant_bacteriuria"] = df["max_log_cfu"].fillna(0) >= 5
    # результатная диссоциация: ОАМ отрицателен, посев положителен
    df["result_dissociation"] = (
        (df["oam_positive"] == False) & (df["mi_positive"] == True)  # noqa: E712
    )
    # временная диссоциация: ОАМ и МИ в разные даты
    df["temporal_dissociation"] = (df["oam_mi_gap_days"].fillna(0) > 0)
    # бинарь профилактики
    df["any_prophylaxis"] = df["proph_regimen"] != "none"
    return df
