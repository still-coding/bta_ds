# ---
# jupyter:
#   jupytext:
#     text_representation:
#       format_name: percent
#   kernelspec:
#     display_name: Python 3
#     name: python3
# ---

# %% [markdown]
# # Анализ антибиотикопрофилактики при БТА — рабочий ноутбук
#
# **Принцип гибридного подхода:** весь «тяжёлый» детерминированный код
# (парсинг, дедупликация, статистика) живёт в протестированном пакете
# `src/bta_study`. Ноутбук — *тонкий слой* поверх него: импорт, исследование,
# визуализация, нарратив. Здесь нет копипаста логики — только её использование.
#
# Почему так, а не «весь анализ в ноутбуке»: ноутбук со скрытым состоянием и
# выполнением ячеек не по порядку — это ровно тот «поток сознания», который
# в реальном кейсе приводил к бесконечным «пересчитываю, чтобы согласовать
# числа». Тестируемое ядро + тонкий ноутбук убирают эту проблему.

# %%
from pathlib import Path
import sys

ROOT = Path.cwd()
if (ROOT / "src").exists():
    sys.path.insert(0, str(ROOT))
elif (ROOT.parent / "src").exists():       # запуск из notebooks/
    ROOT = ROOT.parent
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.bta_study import pipeline, stats

pd.set_option("display.max_columns", 40)

# %% [markdown]
# ## 1. Запуск пайплайна (единый источник чисел)
# Одна функция прогоняет ingest → features → dedup → validate → stats.

# %%
res = pipeline.run(ROOT / "data" / "raw", ROOT / "config" / "protocol.yaml")
df = res.analytical
print("Происхождение чисел:", res.provenance)
df.head()

# %% [markdown]
# ## 2. Характеристика когорты

# %%
print(f"Процедур: {len(df)} | пациентов: {df['name_cell'].str.extract(r'^([А-ЯЁA-Z\\-]+)')[0].nunique()}")
print("Возраст: медиана {:.0f} (IQR {:.0f}–{:.0f})".format(
    df['age'].median(), df['age'].quantile(.25), df['age'].quantile(.75)))
print("Пол:", df['sex'].value_counts().to_dict())
print("Дренаж:", df['drainage'].value_counts().to_dict())
print("Источник возраста:", df['age_source'].value_counts().to_dict())

# %% [markdown]
# ## 3. Сроки скрининга: ОАМ vs посев до БТА
# Ключевая организационная находка — посев выполняется задолго до процедуры.

# %%
t = res.timing
print(f"ОАМ медиана {t['oam_median']:.0f} сут, посев медиана {t['mi_median']:.0f} сут")
if "wilcoxon_p" in t:
    print(f"Парный Wilcoxon p = {t['wilcoxon_p']:.4g}")

fig, ax = plt.subplots(figsize=(7, 4))
pair = df.dropna(subset=["oam_to_bta_days", "mi_to_bta_days"])
ax.boxplot([pair["oam_to_bta_days"], pair["mi_to_bta_days"]],
           tick_labels=["ОАМ", "Посев (МИ)"])
ax.set_ylabel("Дней до БТА")
ax.set_title("Сроки выполнения скрининга до процедуры")
plt.tight_layout(); plt.show()

# %% [markdown]
# ## 4. Диссоциация ОАМ и посева (McNemar)
# Главная клиническая находка: ОАМ систематически пропускает рост,
# выявляемый посевом.

# %%
mc = res.mcnemar
print(f"Пар с обоими тестами: {mc['n_pairs']}")
print(f"ОАМ−/посев+ : {mc['oam_neg_mi_pos']}   (ОАМ пропустил рост)")
print(f"ОАМ+/посев− : {mc['oam_pos_mi_neg']}")
print(f"McNemar exact p = {mc['p_value']:.4g}")
print(mc["discordance_note"])

ct = pd.DataFrame(mc["table"],
                  index=["ОАМ+", "ОАМ−"], columns=["посев+", "посев−"])
ct

# %% [markdown]
# ## 5. Первичная конечная точка — частота ИМВП за 5 суток
# Сравниваем три способа оценки доли: Wilson, точный (Clopper-Pearson),
# байесовский. При малом числе событий байес честнее.

# %%
p = res.primary
for label, key in [("Wilson", "uti_rate_wilson"), ("Clopper-Pearson", "uti_rate_exact")]:
    r = p[key]
    print(f"{label:16s}: {r['point']:.1%}  CI95 [{r['ci_low']:.1%}; {r['ci_high']:.1%}]")
b = p["uti_rate_bayes"]
print(f"{'Bayes Beta(1,1)':16s}: {b['posterior_mean']:.1%}  HDI95 [{b['hdi_low']:.1%}; {b['hdi_high']:.1%}]")
print()
print(stats.power_warning(p["uti_events"], p["n_evaluable"]))

# %%
# Визуализация апостериорного распределения доли ИМВП
from scipy import stats as sps
a_post = 1 + p["uti_events"]
b_post = 1 + (p["n_evaluable"] - p["uti_events"])
xs = np.linspace(0, 0.3, 400)
plt.figure(figsize=(7, 4))
plt.plot(xs, sps.beta(a_post, b_post).pdf(xs))
plt.axvline(b["hdi_low"], ls="--", c="gray")
plt.axvline(b["hdi_high"], ls="--", c="gray")
plt.title("Апостериорное распределение частоты ИМВП (Beta-Binomial)")
plt.xlabel("Частота ИМВП за 5 суток"); plt.ylabel("Плотность")
plt.tight_layout(); plt.show()

# %% [markdown]
# ## 6. Факторы и исход (Fisher) — строго как гипотезы
# Все ассоциации при таком числе событий статистически незначимы;
# направления интерпретируем осторожно.

# %%
fisher_df = pd.DataFrame([
    {"factor": k, "OR": v["odds_ratio"], "p": v["p_value"], "n": v["n"]}
    for k, v in res.fisher.items()
])
fisher_df

# %% [markdown]
# ## 7. Динамика микрофлоры у повторных пациентов

# %%
res.repeat

# %% [markdown]
# ## 8. Что даёт такой пайплайн
# - Любое изменение протокола (`config/protocol.yaml`) перепроливает весь
#   анализ — без правок в коде.
# - Отчёт, слайды и этот ноутбук берут числа из ОДНОГО объекта `res`.
# - Артефакты данных ловятся тестами и схемой, а не глазами по ходу.
