"""
Оркестрация пайплайна: ingest -> features -> dedup -> validate -> stats.
Каждый этап — чистая функция; результат складывается в один объект Results,
на который ссылаются и отчёт, и notebook, и тесты. Это «единый источник чисел»,
отсутствие которого в реальном чате вызывало бесконечные пересчёты.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from . import ingest, features, dedup, schema, stats


@dataclass
class Results:
    config: dict
    analytical: pd.DataFrame              # финальная таблица процедур
    primary: dict
    mcnemar: dict
    timing: dict
    fisher: dict                          # фактор -> результат
    repeat: pd.DataFrame
    provenance: dict = field(default_factory=dict)


def load_config(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(raw_dir: Path, config_path: Path, *, validate_schema: bool = True) -> Results:
    cfg = load_config(config_path)

    # 1) ingestion
    raw = ingest.load_raw(raw_dir)

    # 2) feature engineering
    feat = features.build_features(raw)

    # 3) дедупликация по объявленной единице анализа
    if cfg["study"]["unit_of_analysis"] == "procedure":
        clean = dedup.deduplicate(feat, bta_date_col="bta_date")
    else:
        clean = feat.copy()
    n_removed = clean.attrs.get("n_removed_duplicates", 0)

    # 4) фильтр включения (возраст 18+; неизвестный возраст оставляем, помечая)
    min_age = cfg["study"]["inclusion"]["min_age"]
    excluded_age = int(((clean["age"].notna()) & (clean["age"] < min_age)).sum())
    clean = clean[(clean["age"].isna()) | (clean["age"] >= min_age)].reset_index(drop=True)

    # 5) валидация контракта
    if validate_schema:
        schema.validate(clean)

    # 6) статистика
    primary = stats.primary_endpoint(clean)
    mc = stats.oam_vs_mi_mcnemar(clean)
    timing = stats.oam_vs_mi_timing(clean)
    fisher = {
        f: stats.fisher_factor(clean, f)
        for f in ["any_prophylaxis", "resistant_noted",
                  "significant_bacteriuria"]
        if f in clean.columns
    }
    repeat = stats.repeat_dynamics(clean)

    return Results(
        config=cfg,
        analytical=clean,
        primary=primary,
        mcnemar=mc,
        timing=timing,
        fisher=fisher,
        repeat=repeat,
        provenance={
            "n_raw_rows": len(raw),
            "n_after_dedup": len(feat) - n_removed,
            "n_duplicates_removed": n_removed,
            "n_excluded_under_age": excluded_age,
            "n_analytical": len(clean),
        },
    )


def save_outputs(res: Results, out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    # аналитическая таблица
    p = out_dir / "analytical.csv"
    res.analytical.to_csv(p, index=False)
    paths["analytical"] = p
    # сводка статистики в JSON
    import json
    summary = {
        "provenance": res.provenance,
        "primary": res.primary,
        "mcnemar": res.mcnemar,
        "timing": res.timing,
        "fisher": res.fisher,
    }
    p = out_dir / "summary.json"
    p.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    paths["summary"] = p
    p = out_dir / "repeat_dynamics.csv"
    res.repeat.to_csv(p, index=False)
    paths["repeat"] = p
    return paths
