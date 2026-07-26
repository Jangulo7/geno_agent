"""WP8 --- judge-metric provenance, the triage claim, and ablation error handling.

Three reporting defects, all fixable from saved artefacts with no new API spend:

WP8-A  No faithfulness number in the manuscript can be mapped to a run, and none
       carries an interval. This emits a run x n x unit x cohort table with
       bootstrap CIs from the saved per-case judge scores.

WP8-B  "Both judges independently predicted top-1 correctness with a 33-39 pp
       gap" rests on a post-hoc dichotomisation at an unstated threshold. For a
       clinical-deployment claim the reportable quantities are AUROC with a CI,
       calibration, and precision/recall at the proposed operating point. The
       separate Deployment claim about routing predictions "below 0.8 confidence"
       is characterised here from the saved per-gene confidence scores.

WP8-C  The ablation table conflates format compliance with ranking ability:
       Qwen3-32B returned no parseable ranking on 66 of 300 cases, so its 0.563
       is an as-run deployability figure, not a capability estimate. Both are
       reported.

Outputs ``reports/p2_revision/wp8_judge_provenance.json``. Seed 42.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    EVAL_HARD,
    EVAL_STD,
    REPO,
    SEED,
    load_cases,
    load_ranks,
    write_json,
)

N_BOOT = 10_000
RNG = np.random.default_rng(SEED)

JUDGE_RUNS = [
    # (label, path, cohort, unit scored, metrics)
    (
        "ragas_top1only_n100_standard",
        EVAL_STD / "ragas_top1only_cell_S_n100.json",
        "standard",
        "rank-1 rationale only",
    ),
    (
        "ragas_full_n600_standard",
        EVAL_STD / "ragas_cell_S_n600.json",
        "standard",
        "full response (all ranked genes)",
    ),
    (
        "ragas_top1only_n100_hard",
        EVAL_HARD / "ragas_top1only_cell_S_n100.json",
        "hard",
        "rank-1 rationale only",
    ),
    (
        "ragas_full_n600_hard",
        EVAL_HARD / "ragas_cell_S_n600.json",
        "hard",
        "full response (all ranked genes)",
    ),
]

CONTEXT_CAP = 20  # chunks per case supplied to the judge (LEA itself used up to 45)


def boot_ci(vals: np.ndarray, n_boot: int = N_BOOT, seed: int = SEED):
    rng = np.random.default_rng(seed)
    vals = np.asarray(vals, dtype=float)
    vals = vals[~np.isnan(vals)]
    if len(vals) == 0:
        return float("nan"), float("nan"), float("nan")
    idx = rng.integers(0, len(vals), size=(n_boot, len(vals)))
    means = vals[idx].mean(axis=1)
    return float(vals.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def cluster_boot_ci(case_ids, vals, n_boot: int = N_BOOT, seed: int = SEED):
    """Publication-clustered bootstrap for a judge mean."""
    rng = np.random.default_rng(seed)
    pm = {c.case_id: c.source_pmid for c in load_cases()}
    groups: dict[str, list[float]] = {}
    for cid, v in zip(case_ids, vals, strict=True):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        groups.setdefault(pm.get(cid, cid), []).append(float(v))
    keys = list(groups)
    if not keys:
        return float("nan"), float("nan"), float("nan")
    flat = np.array([v for k in keys for v in groups[k]])
    point = float(flat.mean())
    draws = np.empty(n_boot)
    for b in range(n_boot):
        picks = rng.integers(0, len(keys), size=len(keys))
        vs = [v for i in picks for v in groups[keys[i]]]
        draws[b] = float(np.mean(vs))
    return point, float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def judge_table() -> list[dict]:
    rows = []
    for label, path, cohort, unit in JUDGE_RUNS:
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        per = doc["per_case"]
        metrics = doc.get("metrics", [])
        entry = {
            "run": label,
            "file": str(path.relative_to(REPO)),
            "cohort": cohort,
            "unit_scored": unit,
            "judge_model": doc.get("judge_model"),
            "judge_temperature": doc.get("judge_temperature"),
            "sampling_frame": "MONDO-stratified subsample of the n=1,047 cohort, seed 42",
            "n_requested": doc.get("n_cases_total"),
            "n_evaluated": doc.get("n_cases_evaluated", len(per)),
            "n_skipped": doc.get("n_cases_skipped", 0),
            "context_cap_chunks": CONTEXT_CAP,
            "metrics": {},
        }
        for m in metrics:
            vals = [c.get(m) for c in per]
            cids = [c.get("case_id") for c in per]
            mean, lo, hi = boot_ci(np.array([v for v in vals if v is not None], dtype=float))
            _cmean, clo, chi = cluster_boot_ci(cids, vals)
            entry["metrics"][m] = {
                "mean": round(mean, 4),
                "ci95_case_bootstrap": [round(lo, 4), round(hi, 4)],
                "ci95_cluster_bootstrap": [round(clo, 4), round(chi, 4)],
                "n": int(sum(1 for v in vals if v is not None)),
            }
        rows.append(entry)
    return rows


def triage_analysis() -> dict:
    """WP8-B --- operating characteristics of faithfulness as a triage signal."""
    from sklearn.metrics import (
        precision_recall_curve,
        roc_auc_score,
        roc_curve,
    )

    out = {}
    top1 = {cid: int(r is not None and r <= 1) for cid, r in load_ranks("S").items()}

    for label, path, cohort, _unit in JUDGE_RUNS:
        if cohort != "standard" or not path.exists():
            continue
        doc = json.loads(path.read_text())
        per = doc["per_case"]
        pairs = [
            (c["case_id"], c.get("faithfulness"))
            for c in per
            if c.get("faithfulness") is not None and c["case_id"] in top1
        ]
        if not pairs:
            continue
        ids = [p[0] for p in pairs]
        score = np.array([p[1] for p in pairs], dtype=float)
        y = np.array([top1[i] for i in ids], dtype=int)
        if len(set(y.tolist())) < 2:
            continue

        auc = float(roc_auc_score(y, score))
        # cluster bootstrap for the AUROC
        pm = {c.case_id: c.source_pmid for c in load_cases()}
        groups: dict[str, list[int]] = {}
        for k, i in enumerate(ids):
            groups.setdefault(pm[i], []).append(k)
        keys = list(groups)
        rng = np.random.default_rng(SEED)
        draws = []
        for _ in range(2000):
            picks = rng.integers(0, len(keys), size=len(keys))
            sel = [k for p in picks for k in groups[keys[p]]]
            ys, ss = y[sel], score[sel]
            if len(set(ys.tolist())) < 2:
                continue
            draws.append(roc_auc_score(ys, ss))
        auc_lo, auc_hi = (
            (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
            if draws
            else (float("nan"), float("nan"))
        )

        # The manuscript's dichotomisation, made explicit. Youden-optimal threshold
        # is reported alongside the median split actually used.
        fpr, tpr, thr = roc_curve(y, score)
        youden = thr[int(np.argmax(tpr - fpr))]
        median_thr = float(np.median(score))

        ops = {}
        for name, t in (("median_split", median_thr), ("youden_optimal", float(youden))):
            high = score >= t
            n_hi, n_lo = int(high.sum()), int((~high).sum())
            if n_hi == 0 or n_lo == 0:
                continue
            acc_hi = float(y[high].mean())
            acc_lo = float(y[~high].mean())
            tp = int(((score >= t) & (y == 1)).sum())
            fp = int(((score >= t) & (y == 0)).sum())
            fn = int(((score < t) & (y == 1)).sum())
            ops[name] = {
                "threshold": round(float(t), 4),
                "n_above": n_hi,
                "n_below": n_lo,
                "top1_accuracy_above": round(acc_hi, 4),
                "top1_accuracy_below": round(acc_lo, 4),
                "gap_pp": round((acc_hi - acc_lo) * 100, 1),
                "precision_above": round(tp / (tp + fp), 4) if (tp + fp) else None,
                "recall_above": round(tp / (tp + fn), 4) if (tp + fn) else None,
            }

        # calibration in equal-count bins
        order = np.argsort(score)
        bins = np.array_split(order, 4)
        calib = [
            {
                "bin": i + 1,
                "n": len(b),
                "mean_faithfulness": round(float(score[b].mean()), 4),
                "observed_top1": round(float(y[b].mean()), 4),
            }
            for i, b in enumerate(bins)
        ]

        prec, rec, _ = precision_recall_curve(y, score)
        out[label] = {
            "n": len(ids),
            "n_publications": len({pm[i] for i in ids}),
            "prevalence_top1": round(float(y.mean()), 4),
            "auroc": round(auc, 4),
            "auroc_ci95_cluster_bootstrap": [round(auc_lo, 4), round(auc_hi, 4)],
            "auprc": round(float(np.trapezoid(prec[::-1], rec[::-1])), 4),
            "operating_points": ops,
            "calibration_quartiles": calib,
        }
    return out


def confidence_threshold_claim() -> dict:
    """The Deployment section's '<0.8 confidence -> manual review' rule.

    Characterised from the saved per-gene aggregate_confidence of the rank-1 gene.
    """
    top1 = {cid: int(r is not None and r <= 1) for cid, r in load_ranks("S").items()}
    conf, ys = [], []
    cell_dir = EVAL_STD / "cell_S_rerank_inside_plus_lea"
    for c in load_cases():
        p = cell_dir / f"{c.case_id}.json"
        if not p.exists():
            continue
        payload = json.loads(p.read_text())
        rank1 = next((e for e in payload if e.get("final_rank") == 1), None)
        if rank1 is None:
            continue
        conf.append(float(rank1.get("aggregate_confidence", np.nan)))
        ys.append(top1[c.case_id])
    conf_a = np.array(conf, dtype=float)
    y = np.array(ys, dtype=int)
    ok = ~np.isnan(conf_a)
    conf_a, y = conf_a[ok], y[ok]

    from sklearn.metrics import roc_auc_score

    rows = {}
    for t in (0.5, 0.6, 0.7, 0.8, 0.9):
        above = conf_a >= t
        if above.sum() == 0 or (~above).sum() == 0:
            rows[str(t)] = {
                "threshold": t,
                "n_above": int(above.sum()),
                "n_below": int((~above).sum()),
                "degenerate": True,
            }
            continue
        rows[str(t)] = {
            "threshold": t,
            "n_above": int(above.sum()),
            "n_below": int((~above).sum()),
            "share_routed_to_review": round(float((~above).mean()), 4),
            "top1_accuracy_above": round(float(y[above].mean()), 4),
            "top1_accuracy_below": round(float(y[~above].mean()), 4),
            "gap_pp": round(float(y[above].mean() - y[~above].mean()) * 100, 1),
        }
    return {
        "n_cases_with_rank1_confidence": len(conf_a),
        "confidence_distribution": {
            "mean": round(float(conf_a.mean()), 4),
            "median": round(float(np.median(conf_a)), 4),
            "min": round(float(conf_a.min()), 4),
            "max": round(float(conf_a.max()), 4),
            "share_at_or_above_0.8": round(float((conf_a >= 0.8).mean()), 4),
        },
        "auroc_confidence_predicts_top1": round(float(roc_auc_score(y, conf_a)), 4)
        if len(set(y.tolist())) > 1
        else None,
        "thresholds": rows,
    }


def ablation_errors() -> list[dict]:
    """WP8-C --- as-run vs error-excluded top-1 for every ablation model."""
    cases = {c.case_id: c for c in load_cases()}
    absent = {c.case_id for c in cases.values() if c.overlap == 0}

    out = []
    for slug, pretty in (
        ("qwen_qwen3-32b", "Qwen3-32B-Instruct"),
        ("anthropic_claude-sonnet-4.6", "Claude Sonnet 4.6"),
        ("deepseek_deepseek-chat-v3-0324", "DeepSeek-V3-0324"),
    ):
        files = sorted(glob.glob(str(EVAL_STD / f"cell_S_ablation_{slug}" / "*.json")))
        recs = [json.loads(Path(f).read_text()) for f in files]
        n = len(recs)

        def is_error(r):
            return bool(r.get("parse_error")) or bool(r.get("error")) or r.get("top1") is None

        errs = [r for r in recs if is_error(r)]
        okay = [r for r in recs if not is_error(r)]

        def acc(rs):
            return (
                round(float(np.mean([bool(r.get("top1_correct")) for r in rs])), 4) if rs else None
            )

        fair_all = [r for r in recs if r["case_id"] in absent]
        fair_ok = [r for r in okay if r["case_id"] in absent]

        # error taxonomy
        kinds: dict[str, int] = {}
        for r in errs:
            pe = r.get("parse_error") or r.get("error") or "no_top1"
            kind = str(pe).split(":", 1)[0][:40]
            kinds[kind] = kinds.get(kind, 0) + 1

        out.append(
            {
                "model": pretty,
                "slug": slug,
                "n_cases": n,
                "n_errors": len(errs),
                "error_rate": round(len(errs) / n, 4),
                "error_kinds": kinds,
                "overall_top1_as_run": acc(recs),
                "overall_top1_error_excluded": acc(okay),
                "n_scored_error_excluded": len(okay),
                "fair_top1_as_run": acc(fair_all),
                "fair_top1_error_excluded": acc(fair_ok),
                "n_fair": len(fair_all),
                "n_fair_error_excluded": len(fair_ok),
                "mean_latency_s": round(
                    float(np.mean([r.get("latency_s", np.nan) for r in recs])), 2
                ),
                "cost_usd": round(float(np.nansum([r.get("cost_usd", 0.0) for r in recs])), 2),
            }
        )
    return out


def main() -> None:
    payload = {
        "work_package": "WP8",
        "description": (
            "Judge-run provenance with intervals, operating characteristics for the "
            "triage claim, and as-run vs error-excluded ablation estimates."
        ),
        "seed": SEED,
        "n_bootstrap": N_BOOT,
        "note_deepeval": (
            "DeepEval is excluded from this revision. run_deepeval.py scores the "
            "HallucinationMetric, for which higher is worse, but the saved field "
            "aggregate_mean_hallucination_score (0.845) was reported in the "
            "manuscript as a groundedness of 0.845. The judge's own free-text "
            "reasons confirm the direction (a score of 0.98 is accompanied by 'a "
            "high level of contradiction'). Every DeepEval-derived claim is "
            "therefore withdrawn rather than re-signed."
        ),
        "judge_runs": judge_table(),
        "triage": triage_analysis(),
        "deployment_confidence_threshold": confidence_threshold_claim(),
        "ablation": ablation_errors(),
    }
    p = write_json("wp8_judge_provenance.json", payload)
    print(f"wrote {p}")

    print("\n--- judge runs ---")
    for r in payload["judge_runs"]:
        f = r["metrics"].get("faithfulness", {})
        print(
            f"  {r['run']:<32} n={r['n_evaluated']:>3} {r['unit_scored']:<34} "
            f"faithfulness {f.get('mean')} CI {f.get('ci95_cluster_bootstrap')}"
        )

    print("\n--- triage (faithfulness -> top-1) ---")
    for k, v in payload["triage"].items():
        print(f"  {k}: n={v['n']} AUROC={v['auroc']} CI {v['auroc_ci95_cluster_bootstrap']}")
        for name, op in v["operating_points"].items():
            print(
                f"      {name:<16} thr={op['threshold']:.3f} "
                f"acc {op['top1_accuracy_below']:.3f}->{op['top1_accuracy_above']:.3f} "
                f"gap {op['gap_pp']} pp  prec={op['precision_above']} rec={op['recall_above']}"
            )

    dc = payload["deployment_confidence_threshold"]
    print("\n--- deployment confidence rule (rank-1 aggregate_confidence) ---")
    print(f"  distribution: {dc['confidence_distribution']}")
    print(f"  AUROC confidence->top1: {dc['auroc_confidence_predicts_top1']}")
    for k, v in dc["thresholds"].items():
        if v.get("degenerate"):
            print(f"    thr {k}: DEGENERATE (n_above={v['n_above']}, n_below={v['n_below']})")
        else:
            print(
                f"    thr {k}: routes {v['share_routed_to_review']:.1%} to review, "
                f"acc {v['top1_accuracy_below']:.3f} vs {v['top1_accuracy_above']:.3f}"
            )

    print("\n--- ablation: as-run vs error-excluded ---")
    for r in payload["ablation"]:
        print(
            f"  {r['model']:<22} errors {r['n_errors']:>3}/{r['n_cases']}  "
            f"overall {r['overall_top1_as_run']} -> {r['overall_top1_error_excluded']}  "
            f"fair {r['fair_top1_as_run']} -> {r['fair_top1_error_excluded']}"
        )
        print(f"      error kinds: {r['error_kinds']}")


if __name__ == "__main__":
    main()
