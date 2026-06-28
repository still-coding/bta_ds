"""
Статистический слой. Отдельная важная мысль для малых выборок:
частотный p-value при 3 событиях почти неинформативен. Поэтому рядом с
классическими тестами даём:
  - точные доверительные интервалы (Clopper-Pearson, Wilson),
  - байесовскую апостериорную оценку доли (Beta-Binomial) с интервалом
    наибольшей плотности — она интерпретируема даже на единичных событиях.

Все функции возвращают простые dataclass/словари — их легко положить
и в отчёт, и в notebook, и в тест.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.contingency_tables import mcnemar
from statsmodels.stats.proportion import proportion_confint


# ----------------------- доли и интервалы -----------------------

@dataclass
class Proportion:
    k: int
    n: int
    point: float
    ci_low: float
    ci_high: float
    method: str

    def as_dict(self):
        return asdict(self)


def proportion_ci(k: int, n: int, method: str = "wilson", alpha: float = 0.05
                  ) -> Proportion:
    if n == 0:
        return Proportion(0, 0, float("nan"), float("nan"), float("nan"), method)
    lo, hi = proportion_confint(k, n, alpha=alpha, method=method)
    return Proportion(k, n, k / n, float(lo), float(hi), method)


def bayes_proportion(k: int, n: int, *, prior=(1, 1), cred: float = 0.95
                     ) -> dict:
    """
    Апостериорная доля при Beta(prior) априоре. Возвращает среднее и
    интервал наибольшей плотности (HDI). Работает осмысленно даже при k=0.
    """
    a, b = prior[0] + k, prior[1] + (n - k)
    post = stats.beta(a, b)
    mean = a / (a + b)
    # численный HDI
    xs = np.linspace(0, 1, 10001)
    pdf = post.pdf(xs)
    order = np.argsort(pdf)[::-1]
    cum = np.cumsum(np.sort(pdf)[::-1])
    cum /= cum[-1]
    cutoff = np.searchsorted(cum, cred)
    sel = np.sort(xs[order[:cutoff + 1]])
    return {
        "k": k, "n": n, "posterior_mean": float(mean),
        "hdi_low": float(sel.min()), "hdi_high": float(sel.max()),
        "cred": cred, "prior": prior,
    }


# ----------------------- конечные точки -----------------------

def primary_endpoint(df: pd.DataFrame) -> dict:
    """Первичная: отсутствие симптомной ИМВП в течение 5 суток (без цензуры)."""
    evaluable = df[~df["censored"] & df["uti_5d"].notna()]
    n = len(evaluable)
    events = int((evaluable["uti_5d"] == True).sum())  # noqa: E712
    freq = proportion_ci(events, n, method="wilson")
    exact = proportion_ci(events, n, method="beta")  # Clopper-Pearson
    bayes = bayes_proportion(events, n)
    return {
        "n_total": len(df),
        "n_censored": int(df["censored"].sum()),
        "n_evaluable": n,
        "uti_events": events,
        "uti_rate_wilson": freq.as_dict(),
        "uti_rate_exact": exact.as_dict(),
        "uti_rate_bayes": bayes,
    }


# ----------------------- парный ОАМ vs МИ (McNemar) -----------------------

def oam_vs_mi_mcnemar(df: pd.DataFrame) -> dict:
    """
    Парное сравнение выявления бактериурии: ОАМ vs посев на одних процедурах.
    Главная находка кейса — систематический пропуск роста при ОАМ.
    Таблица сопряжённости 2x2 -> точный тест Мак-Нимара.
    """
    pair = df[df["oam_done"] & df["mi_done"]
              & df["oam_positive"].notna() & df["mi_positive"].notna()].copy()
    oam = pair["oam_positive"] == True   # noqa: E712
    mi = pair["mi_positive"] == True     # noqa: E712
    a = int((oam & mi).sum())            # оба +
    b = int((~oam & mi).sum())           # ОАМ-, МИ+
    c = int((oam & ~mi).sum())           # ОАМ+, МИ-
    d = int((~oam & ~mi).sum())          # оба -
    table = [[a, b], [c, d]]               # порядок входа McNemar (НЕ ОАМ×посев)
    res = mcnemar(table, exact=True)
    # Корректная 2x2 для отображения: строки — ОАМ±, столбцы — посев±.
    contingency = [[a, c], [b, d]]
    return {
        "n_pairs": len(pair),
        "both_positive": a, "oam_neg_mi_pos": b,
        "oam_pos_mi_neg": c, "both_negative": d,
        "table": table,
        "contingency": contingency,
        "statistic": float(res.statistic),
        "p_value": float(res.pvalue),
        "discordance_note": (
            f"ОАМ пропустил рост в {b} из {b + a} случаев положительного посева"
            if (b + a) else "нет положительных посевов в паре"
        ),
    }


# ----------------------- сроки ОАМ vs МИ (Wilcoxon) -----------------------

def oam_vs_mi_timing(df: pd.DataFrame) -> dict:
    """Сравнение сроков выполнения ОАМ и МИ до БТА (парный Wilcoxon)."""
    pair = df.dropna(subset=["oam_to_bta_days", "mi_to_bta_days"])
    oam = pair["oam_to_bta_days"].to_numpy(dtype=float)
    mi = pair["mi_to_bta_days"].to_numpy(dtype=float)
    out = {
        "n_pairs": len(pair),
        "oam_median": float(np.median(oam)) if len(oam) else None,
        "mi_median": float(np.median(mi)) if len(mi) else None,
        "oam_iqr": [float(np.percentile(oam, 25)), float(np.percentile(oam, 75))] if len(oam) else None,
        "mi_iqr": [float(np.percentile(mi, 25)), float(np.percentile(mi, 75))] if len(mi) else None,
    }
    if len(pair) >= 5 and np.any(oam != mi):
        w = stats.wilcoxon(oam, mi)
        out["wilcoxon_stat"] = float(w.statistic)
        out["wilcoxon_p"] = float(w.pvalue)
    return out


# ----------------------- факторы vs исход (Fisher) -----------------------

def fisher_factor(df: pd.DataFrame, factor: str) -> dict:
    """
    Точный тест Фишера: бинарный фактор vs первичный исход (ИМВП).
    factor должен быть булевой колонкой. Включаем только оцениваемые процедуры.
    """
    ev = df[~df["censored"] & df["uti_5d"].notna()].copy()
    ev["_f"] = ev[factor].astype(bool)
    ev["_y"] = (ev["uti_5d"] == True)  # noqa: E712
    a = int((ev["_f"] & ev["_y"]).sum())
    b = int((ev["_f"] & ~ev["_y"]).sum())
    c = int((~ev["_f"] & ev["_y"]).sum())
    d = int((~ev["_f"] & ~ev["_y"]).sum())
    odds, p = stats.fisher_exact([[a, b], [c, d]])
    return {
        "factor": factor, "table": [[a, b], [c, d]],
        "odds_ratio": float(odds) if np.isfinite(odds) else None,
        "p_value": float(p),
        "n": a + b + c + d,
    }


# ----------------------- мощность / предупреждение -----------------------

def power_warning(n_events: int, n: int) -> str:
    if n_events <= 5:
        return (f"Всего {n_events} событий на {n} наблюдений — статистическая "
                f"мощность критически низкая. Незначимые p-value НЕ означают "
                f"отсутствия эффекта; направления трактуются как гипотезы.")
    return f"{n_events} событий на {n} наблюдений."


# ----------------------- повторные пациенты -----------------------

def repeat_dynamics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Динамика колонизатора у пациентов с >1 процедурой:
    тип изменения между последовательными визитами.
    """
    work = df.dropna(subset=["bta_date"]).copy()
    work["last_name"] = work["name_cell"].str.extract(r"^\s*([А-ЯЁA-Z\-]{2,})")
    counts = work["last_name"].value_counts()
    repeaters = counts[counts > 1].index
    records = []
    for ln in repeaters:
        visits = work[work["last_name"] == ln].sort_values("bta_date")
        prev = None
        for _, v in visits.iterrows():
            org_str = v["organisms"]
            org_str = "" if (org_str is None or (isinstance(org_str, float) and org_str != org_str)) else str(org_str)
            cur = set(org_str.split(";")) - {""}
            if prev is not None:
                if not cur and prev:
                    change = "elimination"
                elif cur == prev:
                    change = "persistence"
                elif cur & prev and cur != prev:
                    change = "acquisition" if cur - prev else "partial_loss"
                elif cur and prev and not (cur & prev):
                    change = "full_switch"
                else:
                    change = "appearance"
                records.append({
                    "patient": ln, "date": v["bta_date"],
                    "prev_organisms": ";".join(sorted(prev)) or "—",
                    "cur_organisms": ";".join(sorted(cur)) or "—",
                    "change": change,
                })
            prev = cur
    return pd.DataFrame(records)
