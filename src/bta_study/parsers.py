"""
Чистые функции парсинга. Принцип: КАЖДОЕ преобразование «грязь -> структура»
— это отдельная функция без побочных эффектов, которую можно покрыть тестом.

Именно отсутствие этого слоя в реальном чате приводило к циклу
«нашли артефакт -> поправили руками -> пересчитали весь анализ».
Здесь артефакт ловится один раз тестом и больше не возвращается.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

_EXCEL_EPOCH = dt.date(1899, 12, 30)


def _s(x) -> str:
    """Безопасное приведение к строке: NaN/None -> ''."""
    if x is None:
        return ""
    if isinstance(x, float) and x != x:  # NaN
        return ""
    return str(x)


# -------------------- ДАТЫ --------------------

_DATE_RE = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})")


def _normalize_year(y: int) -> int:
    if y < 100:                 # двузначный год: 25 -> 2025
        return 2000 + y
    if 1900 <= y <= 1925:       # опечатка вида 1925 вместо 2025 г.р. невозможна,
        return y                #   но реальные годы рождения 19xx оставляем как есть
    return y


def parse_date(value) -> dt.date | None:
    """
    Универсальный парсер даты: понимает Excel serial number (int/float),
    объект date/datetime и строки 'DD.MM.YYYY' / 'DD.MM.YY'.
    Возвращает None для пустых/непарсимых значений.
    """
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)):
        # Excel serial: правдоподобный диапазон 1990..2035 гг.
        if 32000 < value < 50000:
            return _EXCEL_EPOCH + dt.timedelta(days=int(value))
        return None
    s = str(value).strip()
    if not s:
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), _normalize_year(int(m.group(3)))
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def fix_year_typo(d: dt.date | None, *, valid=(2024, 2025, 2026)) -> dt.date | None:
    """
    Чинит опечатки в годе процедуры (напр. 2125 -> 2025), не трогая остальное.
    Решение детерминированное и логируемое, а не «поправил руками».
    """
    if d is None:
        return None
    if d.year in valid:
        return d
    for vy in valid:
        if d.year % 100 == vy % 100:   # совпадение по последним двум цифрам
            return d.replace(year=vy)
    return d


# -------------------- ВОЗРАСТ --------------------

_BIRTH_RE = re.compile(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\s*г\.?\s*р\.?", re.I)


def parse_birth_from_name(name_cell: str) -> dt.date | None:
    """Достаёт дату рождения из текстовой ячейки ФИО ('... 08.05.1976 г.р., ...')."""
    if not isinstance(name_cell, str):
        return None
    m = _BIRTH_RE.search(name_cell)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def age_at(birth: dt.date | None, on: dt.date | None) -> int | None:
    if birth is None or on is None:
        return None
    return (on - birth).days // 365


def resolve_age(
    age_value, name_cell: str, bta_date: dt.date | None
) -> tuple[int | None, str]:
    """
    Приводит возраст к числу по приоритету:
      1) рассчитанный из ДР на дату БТА (источник истины),
      2) явно указанное число (если ДР нет).
    Возвращает (возраст, источник). Источник нужен для аудита расхождений.
    """
    birth = parse_birth_from_name(name_cell)
    derived = age_at(birth, bta_date)
    explicit = None
    try:
        if age_value not in (None, "") and not (isinstance(age_value, float) and age_value != age_value):
            explicit = int(float(age_value))
    except (ValueError, TypeError):
        explicit = None

    if derived is not None:
        return derived, "from_birth"
    if explicit is not None:
        return explicit, "explicit"
    return None, "missing"


# -------------------- ДРЕНАЖ --------------------

_DRAINAGE_MAP = [
    (re.compile(r"самокатетер", re.I), "intermittent"),
    (re.compile(r"постоянн", re.I), "indwelling"),
    (re.compile(r"цистостом", re.I), "cystostomy"),
    (re.compile(r"памперс|подгузник", re.I), "pads"),
]


def parse_drainage(name_cell: str) -> str:
    if not isinstance(name_cell, str):
        return "unknown"
    for rx, label in _DRAINAGE_MAP:
        if rx.search(name_cell):
            return label
    return "unknown"


# -------------------- АНТИБИОТИКИ --------------------

_AB_TABLE = [
    (re.compile(r"нет|^$|не\s+провод", re.I), "none", None),
    (re.compile(r"нитрофуран.*\+|.*\+.*нитрофуран|цефтриаксон.*\+|.*\+.*цефтриаксон|авибактам", re.I), "combined", None),
    (re.compile(r"недел|дн(ей|я)|3\s*недел|7\s*дн", re.I), "prolonged", None),
    (re.compile(r"цефтриаксон", re.I), "single", "ceftriaxone"),
    (re.compile(r"фосфомицин", re.I), "single", "fosfomycin"),
    (re.compile(r"амикацин", re.I), "single", "amikacin"),
    (re.compile(r"нитрофуран", re.I), "single", "nitrofurantoin"),
]


@dataclass
class Prophylaxis:
    regimen: str          # none / single / prolonged / combined
    drug: str | None
    resistant_noted: bool


def classify_prophylaxis(text: str, micro_text: str = "") -> Prophylaxis:
    s = _s(text).strip()
    resistant = bool(re.search(r"устойчив|резистент|нечувствит", _s(micro_text), re.I))
    if not s or re.fullmatch(r"нет\.?", s, re.I):
        return Prophylaxis("none", None, resistant)
    for rx, regimen, drug in _AB_TABLE:
        if rx.search(s):
            # уточняем препарат, даже если режим prolonged/combined
            drug2 = drug
            if drug2 is None:
                for rx2, _, d2 in _AB_TABLE:
                    if d2 and rx2.search(s):
                        drug2 = d2
                        break
            return Prophylaxis(regimen, drug2, resistant)
    return Prophylaxis("single", None, resistant)


# -------------------- МИКРОБИОЛОГИЯ (ОАМ + МИ) --------------------

_TITER_RE = re.compile(r"10\^?(\d+)\s*КОЕ", re.I)
_ORG_RE = re.compile(
    r"(Klebsiella pneumoniae|Escherichia coli|Pseudomonas aeruginosa|"
    r"Enterococcus faecalis|Proteus mirabilis|Acinetobacter baumannii|"
    r"Serratia marcescens)"
)
_INLINE_DATE = re.compile(r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4})")


@dataclass
class Organism:
    name: str
    log10_cfu: int | None


@dataclass
class Microbiology:
    oam_date: dt.date | None
    oam_positive: bool | None       # None == ОАМ не упомянут
    mi_date: dt.date | None
    mi_done: bool
    organisms: list[Organism]

    @property
    def mi_positive(self) -> bool:
        return any(o.log10_cfu is not None for o in self.organisms) or bool(self.organisms)

    @property
    def max_log_cfu(self) -> int | None:
        vals = [o.log10_cfu for o in self.organisms if o.log10_cfu is not None]
        return max(vals) if vals else None


def parse_microbiology(text: str) -> Microbiology:
    """
    Разбирает объединённую ячейку 'бактериурия' на структуру ОАМ и МИ.
    Логика сегментации: ищем фрагменты 'в ОАМ ...' и 'в МИ ...'.
    """
    s = _s(text)
    # --- сегментация по ОАМ / МИ ---
    oam_seg, mi_seg = "", ""
    # делим строку по маркеру 'в МИ' / 'МИ '
    mi_match = re.search(r"(в\s+МИ|,\s*МИ\b|МИ\s)", s, re.I)
    if mi_match:
        oam_seg = s[:mi_match.start()]
        mi_seg = s[mi_match.start():]
    else:
        oam_seg = s

    # --- ОАМ ---
    oam_date = None
    md = _INLINE_DATE.search(oam_seg)
    if md:
        oam_date = parse_date(md.group(1))
    oam_positive = None
    if re.search(r"ОАМ", oam_seg, re.I):
        if re.search(r"отсутств|нет\b|стерил", oam_seg, re.I):
            oam_positive = False
        elif re.search(r"небольшое|единично|присутств|есть|положит|лейкоцит", oam_seg, re.I):
            oam_positive = True
        else:
            oam_positive = None

    # --- МИ ---
    mi_done = bool(re.search(r"МИ", s, re.I)) and not re.search(r"МИ\s+не\s+провод", s, re.I)
    mi_date = None
    organisms: list[Organism] = []
    if mi_done:
        md2 = _INLINE_DATE.search(mi_seg)
        if md2:
            mi_date = parse_date(md2.group(1))
        # разбиваем сегмент МИ на под-фрагменты по запятой и собираем organism+titer
        for chunk in re.split(r",", mi_seg):
            om = _ORG_RE.search(chunk)
            if om:
                tm = _TITER_RE.search(chunk)
                log = int(tm.group(1)) if tm else None
                organisms.append(Organism(om.group(1), log))

    return Microbiology(
        oam_date=oam_date,
        oam_positive=oam_positive,
        mi_date=mi_date,
        mi_done=mi_done,
        organisms=organisms,
    )


# -------------------- ИСХОДЫ --------------------

@dataclass
class Outcome:
    uti_5d: bool | None     # None == исход неизвестен (ранняя выписка / цензура)
    censored: bool
    uti_date: dt.date | None


def parse_uti_outcome(text: str) -> Outcome:
    s = _s(text).strip()
    if not s:
        return Outcome(None, True, None)
    if re.match(r"да\b", s, re.I) or re.search(r"да\s+\d", s, re.I):
        md = _INLINE_DATE.search(s)
        return Outcome(True, False, parse_date(md.group(1)) if md else None)
    if re.search(r"выписан", s, re.I):
        # «нет (выписан через 2 дня)» — наблюдение < 5 суток => цензура
        return Outcome(None, True, None)
    if re.match(r"нет", s, re.I):
        return Outcome(False, False, None)
    return Outcome(None, True, None)


def parse_distant_uti(text: str) -> tuple[bool, dt.date | None]:
    s = _s(text)
    if re.search(r"отдал[её]нн.*ИМВП|ИМВП", s, re.I) and _ORG_RE.search(s):
        md = _INLINE_DATE.search(s)
        return True, parse_date(md.group(1)) if md else None
    return False, None
