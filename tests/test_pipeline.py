"""
Тесты дедупликации и сквозного пайплайна.
Ключевые свойства: идемпотентность и согласованность чисел.
"""
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from src.bta_study import dedup, pipeline, generate

ROOT = Path(__file__).resolve().parents[1]


def test_dedup_removes_cross_table_duplicates():
    df = pd.DataFrame({
        "name_cell": ["КАШКИН С.А., 08.05.1976 г.р."] * 2 + ["ЩУКИН В.Г."],
        "bta_date": [dt.date(2025, 2, 6), dt.date(2025, 2, 6), dt.date(2025, 2, 5)],
        "x": [1, 1, 2],
    })
    out = dedup.deduplicate(df)
    assert len(out) == 2
    assert out.attrs["n_removed_duplicates"] == 1


def test_dedup_idempotent():
    df = pd.DataFrame({
        "name_cell": ["A Б., 01.01.1980 г.р."] * 3,
        "bta_date": [dt.date(2025, 2, 6)] * 3,
        "x": [1, 1, 1],
    })
    once = dedup.deduplicate(df)
    twice = dedup.deduplicate(once)
    assert len(once) == len(twice) == 1


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    raw_dir = tmp_path_factory.mktemp("raw")
    procs = generate.generate(seed=7)
    generate.write_xlsx(procs, raw_dir, seed=7)
    return pipeline.run(raw_dir, ROOT / "config" / "protocol.yaml")


def test_pipeline_runs_and_counts_consistent(results):
    pr = results.provenance
    # число процедур в анализе = сырые - дубликаты - исключённые по возрасту
    assert pr["n_analytical"] == (
        pr["n_raw_rows"] - pr["n_duplicates_removed"] - pr["n_excluded_under_age"]
    )


def test_all_ages_numeric_or_known_missing(results):
    df = results.analytical
    # каждый возраст либо число >=18, либо явно NaN (не строка-дата)
    ages = df["age"].dropna()
    assert (ages >= 18).all()


def test_primary_endpoint_structure(results):
    p = results.primary
    assert p["n_evaluable"] + p["n_censored"] <= p["n_total"]
    assert 0 <= p["uti_rate_exact"]["point"] <= 1


def test_pipeline_deterministic():
    # один и тот же seed -> идентичные числа (воспроизводимость)
    import tempfile
    out = []
    for _ in range(2):
        with tempfile.TemporaryDirectory() as d:
            procs = generate.generate(seed=123)
            generate.write_xlsx(procs, Path(d), seed=123)
            r = pipeline.run(Path(d), ROOT / "config" / "protocol.yaml")
            out.append(r.primary["uti_events"])
    assert out[0] == out[1]
