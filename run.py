"""
Точка входа. Запуск всего пайплайна одной командой:

    python run.py --generate     # сгенерировать синтетические raw-данные
    python run.py                # прогнать анализ на data/raw
    python run.py --no-validate  # без проверки схемы (для отладки)
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
CONFIG = ROOT / "config" / "protocol.yaml"


def main() -> None:
    ap = argparse.ArgumentParser(description="BTA UTI prophylaxis pipeline")
    ap.add_argument("--generate", action="store_true",
                    help="сгенерировать синтетические raw-данные")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    if args.generate:
        from src.bta_study import generate
        procs = generate.generate(seed=args.seed)
        paths = generate.write_xlsx(procs, RAW, seed=args.seed)
        print(f"[generate] процедур (с дубликатами): {len(procs)}")
        for p in paths:
            print("  ->", p.relative_to(ROOT))
        return

    from src.bta_study import pipeline
    res = pipeline.run(RAW, CONFIG, validate_schema=not args.no_validate)
    paths = pipeline.save_outputs(res, PROCESSED)

    pr = res.provenance
    print("=" * 60)
    print("PROVENANCE (происхождение чисел)")
    print(f"  сырых строк (обе таблицы):    {pr['n_raw_rows']}")
    print(f"  удалено дубликатов:           {pr['n_duplicates_removed']}")
    print(f"  исключено по возрасту <18:    {pr['n_excluded_under_age']}")
    print(f"  процедур в анализе:           {pr['n_analytical']}")
    print("=" * 60)

    p = res.primary
    rate = p["uti_rate_exact"]
    by = p["uti_rate_bayes"]
    print("ПЕРВИЧНАЯ КОНЕЧНАЯ ТОЧКА")
    print(f"  оцениваемо процедур: {p['n_evaluable']} (цензурировано {p['n_censored']})")
    print(f"  событий ИМВП: {p['uti_events']}")
    print(f"  частота (Clopper-Pearson 95%): {rate['point']:.1%} "
          f"[{rate['ci_low']:.1%}; {rate['ci_high']:.1%}]")
    print(f"  байес (апостер. среднее, HDI): {by['posterior_mean']:.1%} "
          f"[{by['hdi_low']:.1%}; {by['hdi_high']:.1%}]")
    print("=" * 60)

    mc = res.mcnemar
    print("ОАМ vs ПОСЕВ (McNemar)")
    print(f"  пар: {mc['n_pairs']} | ОАМ−/МИ+: {mc['oam_neg_mi_pos']} "
          f"| ОАМ+/МИ−: {mc['oam_pos_mi_neg']}")
    print(f"  p = {mc['p_value']:.4f} — {mc['discordance_note']}")
    print("=" * 60)

    t = res.timing
    if t["oam_median"] is not None:
        print("СРОКИ ДО БТА (медиана, сут)")
        print(f"  ОАМ: {t['oam_median']:.0f}  |  посев: {t['mi_median']:.0f}"
              + (f"  | Wilcoxon p={t['wilcoxon_p']:.4f}" if "wilcoxon_p" in t else ""))
    print("=" * 60)
    print("Файлы:", ", ".join(str(v.relative_to(ROOT)) for v in paths.values()))


if __name__ == "__main__":
    main()
