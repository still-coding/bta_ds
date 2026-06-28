"""
Тесты слоя парсинга. Каждый артефакт из реальных данных закрыт тестом —
это и есть замена циклу «нашёл руками -> поправил -> снова сломалось».
Запуск: pytest -q
"""
import datetime as dt

import numpy as np
import pytest

from src.bta_study import parsers as P


# ---------- даты ----------

def test_parse_excel_serial():
    # 45964 -> 03.11.2025 (Windows 1900 epoch)
    assert P.parse_date(45964) == dt.date(2025, 11, 3)
    # начало февраля 2025 — другой serial
    assert P.parse_date(45691) == dt.date(2025, 2, 3)

def test_parse_date_string_short_year():
    assert P.parse_date("06.02.25") == dt.date(2025, 2, 6)

def test_parse_date_string_full_year():
    assert P.parse_date("29.08.2025") == dt.date(2025, 8, 29)

def test_parse_date_nan_and_empty():
    assert P.parse_date(np.nan) is None
    assert P.parse_date("") is None
    assert P.parse_date(None) is None

def test_fix_year_typo():
    assert P.fix_year_typo(dt.date(2125, 2, 6)) == dt.date(2025, 2, 6)
    assert P.fix_year_typo(dt.date(2025, 2, 6)) == dt.date(2025, 2, 6)


# ---------- возраст ----------

def test_birth_from_name():
    cell = "КАШКИН С.А., 08.05.1976 г.р., ботулинотерапия 06.02.2025; памперс"
    assert P.parse_birth_from_name(cell) == dt.date(1976, 5, 8)

def test_resolve_age_prefers_birth():
    cell = "КАШКИН С.А., 08.05.1976 г.р., ботулинотерапия 06.02.2025"
    age, src = P.resolve_age(49, cell, dt.date(2025, 2, 6))
    assert age == 48 and src == "from_birth"   # рассчитано из ДР, не из числа

def test_resolve_age_falls_back_to_explicit():
    age, src = P.resolve_age(42, "КУРГУЗОВА Л.В.", dt.date(2025, 2, 25))
    assert age == 42 and src == "explicit"

def test_resolve_age_missing():
    age, src = P.resolve_age("", "БЕЗ ДР", dt.date(2025, 2, 1))
    assert age is None and src == "missing"


# ---------- дренаж ----------

@pytest.mark.parametrize("text,expected", [
    ("... Самокатетеризация", "intermittent"),
    ("... постоянный катетер", "indwelling"),
    ("... цистостома", "cystostomy"),
    ("... памперс", "pads"),
    ("без указания", "unknown"),
])
def test_drainage(text, expected):
    assert P.parse_drainage(text) == expected


# ---------- антибиотики ----------

def test_classify_none():
    assert P.classify_prophylaxis("нет").regimen == "none"
    assert P.classify_prophylaxis("").regimen == "none"

def test_classify_single():
    p = P.classify_prophylaxis("цефтриаксон о/к 2 г")
    assert p.regimen == "single" and p.drug == "ceftriaxone"

def test_classify_prolonged():
    assert P.classify_prophylaxis("нитрофурантоин 7 дней после процедуры").regimen == "prolonged"

def test_classify_combined():
    assert P.classify_prophylaxis("нитрофурантоин + цефтриаксон").regimen == "combined"

def test_resistance_flag():
    p = P.classify_prophylaxis("цефтриаксон", "в МИ Klebsiella устойчив к препарату")
    assert p.resistant_noted is True


# ---------- микробиология ----------

def test_micro_dissociation():
    text = ("в ОАМ 01.02.25 отсутствует, в МИ 27.01.25 "
            "Pseudomonas aeruginosa (10^6 КОЕ/мл)")
    m = P.parse_microbiology(text)
    assert m.oam_positive is False        # ОАМ отрицателен
    assert m.mi_done is True
    assert m.mi_positive is True          # посев положителен
    assert m.max_log_cfu == 6
    assert m.organisms[0].name == "Pseudomonas aeruginosa"
    assert m.oam_date == dt.date(2025, 2, 1)
    assert m.mi_date == dt.date(2025, 1, 27)

def test_micro_polymicrobial():
    text = ("в ОАМ 03.02.25 отсутствует, в МИ 29.01.25 "
            "Enterococcus faecalis (10^6 КОЕ/мл), "
            "Serratia marcescens (10^6 КОЕ/мл)")
    m = P.parse_microbiology(text)
    assert m.n_organisms if hasattr(m, "n_organisms") else len(m.organisms) == 2
    assert len(m.organisms) == 2

def test_micro_mi_not_done():
    text = "небольшое количество в ОАМ 21.01.25, МИ не проводилось"
    m = P.parse_microbiology(text)
    assert m.mi_done is False
    assert m.oam_positive is True


# ---------- исходы ----------

def test_uti_negative():
    o = P.parse_uti_outcome("нет")
    assert o.uti_5d is False and o.censored is False

def test_uti_positive():
    o = P.parse_uti_outcome("да 05.02.2025")
    assert o.uti_5d is True and o.uti_date == dt.date(2025, 2, 5)

def test_uti_censored_discharge():
    o = P.parse_uti_outcome("нет (выписан через 2 дня после процедуры)")
    assert o.censored is True and o.uti_5d is None

def test_distant_uti():
    flag, date = P.parse_distant_uti(
        "отдаленная ИМВП (14.02.26 Klebsiella pneumoniae (10^6 КОЕ/мл))")
    assert flag is True and date == dt.date(2026, 2, 14)
