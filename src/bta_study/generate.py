"""
Генератор синтетического, но «грязного» датасета, структурно идентичного
исходному клиническому Excel (см. скриншот).

Зачем он нужен в проекте:
  - даёт запускаемый код без доступа к реальным персональным данным;
  - воспроизводит ИМЕННО те артефакты, на которых в реальном чате
    спотыкался ad-hoc анализ: даты как Excel serial numbers, возраст внутри
    ФИО, свободный текст в микробиологии, дубликаты процедур между «двумя
    таблицами», опечатки в годах, рассинхрон ОАМ и посева.

Выход: два файла data/raw/raw_1.xlsx и raw_2.xlsx («две таблицы»),
структура столбцов как в оригинале.
"""
from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

# Excel serial date epoch (Windows 1900 system, как в реальном файле)
_EXCEL_EPOCH = dt.date(1899, 12, 30)


def to_excel_serial(d: dt.date) -> int:
    return (d - _EXCEL_EPOCH).days


# --- Контролируемые словари для генерации правдоподобной микробиологии ---
ORGANISMS = [
    "Klebsiella pneumoniae",
    "Escherichia coli",
    "Pseudomonas aeruginosa",
    "Enterococcus faecalis",
    "Proteus mirabilis",
    "Acinetobacter baumannii",
    "Serratia marcescens",
]

ANTIBIOTICS = [
    ("цефтриаксон о/к 2 г", "single", "ceftriaxone"),
    ("цефтриаксон 2 г однократно", "single", "ceftriaxone"),
    ("фосфомицин 3 г однократно", "single", "fosfomycin"),
    ("амикацин 1 г однократно", "single", "amikacin"),
    ("нитрофурантоин 7 дней после процедуры", "prolonged", "nitrofurantoin"),
    ("нитрофурантоин 3 недели после процедуры", "prolonged", "nitrofurantoin"),
    ("нитрофурантоин + цефтриаксон", "combined", "nitrofurantoin"),
    ("цефтазидим-авибактам по поводу КА-ИМВП", "combined", "ceftazidime-avibactam"),
    ("нет", "none", None),
    ("", "none", None),  # пустая ячейка — тоже «нет», но иначе записанная
]

LAST_NAMES = [
    "КАШКИН", "ЩУКИН", "КУРГУЗОВА", "МАРКЕЛОВ", "МАКСИМОВ", "ГОЛУБЕВ",
    "СОБАКИНА", "ШМАКОВ", "ВОРОНЧИХИН", "ВОЕВОДИН", "ЗДОРОВ", "ГАВШИН",
    "БУХГАММЕР", "ЖУМАБЕКОВА", "ЯШИН", "ГРЕЧАНИК", "ГУЗАНОВ", "ГОРЯЕВ",
]


@dataclass
class Patient:
    last_name: str
    initials: str
    birth: dt.date
    sex: str
    drainage: str  # самокатетеризация / постоянный катетер / цистостома / памперс
    # стабильный колонизатор пациента (для повторных визитов)
    colonizer: str


def _rand_birth(rng: random.Random) -> dt.date:
    # возраст строго 18+ на момент процедур 2025-2026
    year = rng.randint(1958, 2007)
    return dt.date(year, rng.randint(1, 12), rng.randint(1, 28))


_EXTRA_STEMS = [
    "Гречихин", "Лапшин", "Орлова", "Седов", "Туманов", "Фомина", "Цапля",
    "Чижов", "Шубин", "Юдина", "Беляев", "Власова", "Дроздов", "Ежов",
    "Зимин", "Ильина", "Котов", "Лосева", "Мальцев", "Носов", "Панкова",
    "Рыбин", "Соловьёв", "Тихонов", "Ушаков", "Фролова", "Хомяков", "Цветков",
    "Чернова", "Шилов", "Яковлев", "Авдеев", "Бобров", "Гусев",
]


def build_patients(rng: random.Random) -> list[Patient]:
    drainages = [
        "Самокатетеризация", "самокатетеризация", "постоянный катетер",
        "цистостома", "памперс",
    ]
    pts = []
    all_names = LAST_NAMES + [s.upper() for s in _EXTRA_STEMS]
    for ln in all_names:
        pts.append(
            Patient(
                last_name=ln,
                initials=f"{rng.choice('АВСДЕМНП')}.{rng.choice('АВСДЕМНП')}.",
                birth=_rand_birth(rng),
                sex=rng.choice(["м", "м", "ж"]),  # перекос в мужчин, как в когорте СТ
                drainage=rng.choice(drainages),
                colonizer=rng.choice(ORGANISMS),
            )
        )
    return pts


def _fmt_titer(rng: random.Random) -> tuple[int, str]:
    """Возвращает (log10_cfu, строка '10^N КОЕ/мл')."""
    log = rng.choice([2, 3, 4, 5, 6, 6, 7])  # перекос к высоким титрам (катетер-зависимые)
    return log, f"(10^{log} КОЕ/мл)"


def _make_microbiology_cell(
    rng: random.Random,
    bta_date: dt.date,
    colonizer: str,
    *,
    dissociation: bool,
    mi_done: bool,
) -> str:
    """
    Собирает свободнотекстовую ячейку 'бактериурия', объединяющую ОАМ и МИ —
    ровно как в оригинале. Намеренно вводит:
      - разные даты для ОАМ и МИ (рассинхрон),
      - результатную диссоциацию (ОАМ отрицателен, МИ положителен),
      - иногда 'МИ не проводилось'.
    """
    oam_date = bta_date - dt.timedelta(days=rng.randint(1, 9))
    parts = []

    if dissociation:
        # ОАМ отрицателен, но посев положителен — ключевая находка реального кейса
        parts.append(f"в ОАМ {oam_date:%d.%m.%y} отсутствует")
        if mi_done:
            mi_date = bta_date - dt.timedelta(days=rng.randint(1, 40))
            _, titer = _fmt_titer(rng)
            parts.append(f"в МИ {mi_date:%d.%m.%y} {colonizer} {titer}")
        else:
            parts.append("МИ не проводилось")
    else:
        if rng.random() < 0.5:
            parts.append(f"небольшое количество в ОАМ {oam_date:%d.%m.%y}")
        else:
            parts.append(f"в ОАМ {oam_date:%d.%m.%y} единично")
        if mi_done:
            mi_date = bta_date - dt.timedelta(days=rng.randint(1, 40))
            organisms = [colonizer]
            # иногда полимикробная картина
            if rng.random() < 0.3:
                organisms.append(rng.choice([o for o in ORGANISMS if o != colonizer]))
            chunk = ", ".join(
                f"{o} {_fmt_titer(rng)[1]}" for o in organisms
            )
            parts.append(f"в МИ {mi_date:%d.%m.%y} {chunk}")
            # иногда явная пометка о резистентности
            if rng.random() < 0.15:
                parts.append("устойчив к назначенному препарату")
        else:
            parts.append("МИ не проводилось")
    return ", ".join(parts)


@dataclass
class Procedure:
    patient: Patient
    bta_date: dt.date
    age_value: object  # число / пусто
    prophylaxis: str
    microbiology: str
    oam_lab_no: object
    uti_5d: str
    post_culture: str
    post_lab_no: object
    organism_col: str
    other: str
    sheet: int = 1
    serial_as_int: bool = True  # дата БТА как Excel serial (грязь) vs строка


def _name_cell(p: Patient, bta_date: dt.date, rng: random.Random, *,
               age_in_name: bool) -> str:
    """ФИО + ДР + анамнез — возраст «спрятан» в ДР внутри текстовой ячейки."""
    base = (f"{p.last_name} {p.initials}, {p.birth:%d.%m.%Y} г.р., "
            f"ботулинотерапия {bta_date:%d.%m.%Y}; {p.drainage}")
    return base


def generate(seed: int = 42, n_procedures: int = 64) -> list[Procedure]:
    rng = random.Random(seed)
    patients = build_patients(rng)

    # назначим часть пациентов «повторными» (2-3 визита)
    repeat_pool = rng.sample(patients, 12)
    procedures: list[Procedure] = []

    def one_procedure(p: Patient, bta_date: dt.date) -> Procedure:
        ab_text, ab_kind, _ = rng.choice(ANTIBIOTICS)
        dissociation = rng.random() < 0.45  # высокая доля диссоциации, как в кейсе
        mi_done = rng.random() < 0.7        # ~30% без посева
        micro = _make_microbiology_cell(
            rng, bta_date, p.colonizer,
            dissociation=dissociation, mi_done=mi_done,
        )

        # первичный исход: в основном без ИМВП; редкие события + цензура
        roll = rng.random()
        if roll < 0.06:
            uti = f"да {bta_date + dt.timedelta(days=rng.randint(1,5)):%d.%m.%Y}"
        elif roll < 0.30:
            uti = f"нет (выписан через {rng.randint(1,2)} дня после процедуры)"
        else:
            uti = "нет"

        # возраст: чаще пусто (заставляем выводить из ДР), иногда заполнен,
        # иногда заполнен с ошибкой (несогласован с ДР)
        age_roll = rng.random()
        if age_roll < 0.6:
            age = None
        else:
            true_age = (bta_date - p.birth).days // 365
            if age_roll > 0.92:
                age = true_age + rng.choice([-1, 1, 10])  # ошибка ввода
            else:
                age = true_age

        other = ""
        if rng.random() < 0.08:
            far_date = bta_date + dt.timedelta(days=rng.randint(60, 400))
            _, titer = _fmt_titer(rng)
            other = (f"отдаленная ИМВП ({far_date:%d.%m.%y} "
                     f"{rng.choice(ORGANISMS)} {titer})")

        return Procedure(
            patient=p,
            bta_date=bta_date,
            age_value=age,
            prophylaxis=ab_text,
            microbiology=micro,
            oam_lab_no=rng.randint(10_000_000, 70_999_999) if mi_done or rng.random() < .5 else None,
            uti_5d=uti,
            post_culture="нет" if rng.random() < 0.85 else
                         f"да {bta_date + dt.timedelta(days=rng.randint(1,5)):%d.%m.%Y}",
            post_lab_no=rng.randint(10_000_000, 70_999_999) if rng.random() < 0.4 else None,
            organism_col="",
            other=other,
        )

    # одиночные процедуры
    singles = [p for p in patients if p not in repeat_pool]
    for p in singles:
        d = dt.date(2025, rng.randint(2, 12), rng.randint(1, 28))
        procedures.append(one_procedure(p, d))

    # повторные процедуры: интервал ~ длительность эффекта (4-9 мес)
    for p in repeat_pool:
        d0 = dt.date(2025, rng.randint(2, 6), rng.randint(1, 28))
        n_visits = 3 if p.last_name == "КАШКИН" else 2
        cur = d0
        for _ in range(n_visits):
            procedures.append(one_procedure(p, cur))
            cur = cur + dt.timedelta(days=rng.randint(120, 270))

    procedures = procedures[:n_procedures]

    # --- ИНЪЕКЦИЯ АРТЕФАКТОВ ---
    # 1) распределяем по двум «таблицам» (листам/файлам)
    for proc in procedures:
        proc.sheet = 1 if rng.random() < 0.6 else 2

    # 2) даты БТА: часть как Excel serial int, часть как строка (смесь форматов)
    for proc in procedures:
        proc.serial_as_int = rng.random() < 0.7

    # 3) межтабличные дубликаты: копируем несколько процедур во второй лист
    dup_sources = rng.sample(procedures, 4)
    for src in dup_sources:
        dup = Procedure(**{**src.__dict__})
        dup.sheet = 2 if src.sheet == 1 else 1
        procedures.append(dup)

    # 4) опечатка в годе у одной процедуры (как КАШКИН/ЗДОРОВ в оригинале)
    typo = rng.choice([p for p in procedures])
    typo.bta_date = typo.bta_date.replace(year=typo.bta_date.year + 100) \
        if typo.bta_date.year < 1950 else typo.bta_date

    return procedures


COLUMNS = [
    "№", "Фамилия И.О.", "Дата БТА", "пол", "возраст", "а/б профилактика",
    "бактериурия", "№ анализа", "ИМВП в теч. 5 дней после БТА (Да-дата/нет)",
    "Посев после БТА (да-дата/нет)", "Номер анализа", "м/о", "Другое",
]


def write_xlsx(procedures: list[Procedure], out_dir: Path, seed: int = 42) -> list[Path]:
    rng = random.Random(seed + 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for sheet_no in (1, 2):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Таблица {sheet_no}"
        ws.append(COLUMNS)
        rows = [p for p in procedures if p.sheet == sheet_no]
        for i, proc in enumerate(rows, start=1):
            p = proc.patient
            date_cell = (to_excel_serial(proc.bta_date)
                         if proc.serial_as_int
                         else f"{proc.bta_date:%d.%m.%Y}")
            ws.append([
                i,
                _name_cell(p, proc.bta_date, rng, age_in_name=True),
                date_cell,
                p.sex,
                proc.age_value if proc.age_value is not None else "",
                proc.prophylaxis,
                proc.microbiology,
                proc.oam_lab_no if proc.oam_lab_no is not None else "",
                proc.uti_5d,
                proc.post_culture,
                proc.post_lab_no if proc.post_lab_no is not None else "",
                proc.organism_col,
                proc.other,
            ])
        path = out_dir / f"raw_{sheet_no}.xlsx"
        wb.save(path)
        paths.append(path)
    return paths


if __name__ == "__main__":
    procs = generate()
    out = Path(__file__).resolve().parents[2] / "data" / "raw"
    paths = write_xlsx(procs, out)
    print(f"Сгенерировано процедур (с дубликатами): {len(procs)}")
    for p in paths:
        print("  ->", p)
