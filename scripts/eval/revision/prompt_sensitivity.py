"""WP8-D --- prompt-sensitivity replay of the LEA stage.

One prompt at temperature 0 is below current LLM-evaluation reporting standards.
This replays the LLM-as-Evidence-Aggregator stage against paraphrased instruction
prompts on a MONDO-stratified subsample, **reusing the cached retrieval and
rerank** recorded in ``data/eval_1050/cell_S_responses/*.json``. Only the LEA
generation re-runs, so retrieval, reranking, chunk selection and the evidence
text are bit-identical across prompt variants and the contrast isolates prompt
wording.

The three variants differ only in how the ranking instruction is phrased; all
three demand the same JSON array schema, because a variant that changed the
output contract would confound wording with parseability.

Usage:
    python scripts/eval/revision/prompt_sensitivity.py --n 150

Writes ``reports/p2_revision/wp8d_prompt_sensitivity.json`` plus per-case
responses under ``data/eval_1050/prompt_sensitivity/<variant>/``.

Seed 42.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (
    CATEGORIES,
    EVAL_STD,
    SEED,
    load_cases,
    load_ranks,
    subset,
    write_json,
)

VLLM_URL = os.environ.get("VLLM_URL", "http://127.0.0.1:8001/v1/chat/completions")
MODEL = os.environ.get("VLLM_MODEL", "Qwen3-8B")
RESP_DIR = EVAL_STD / "cell_S_responses"
OUT_RESP = EVAL_STD / "prompt_sensitivity"

# Variant "production" is the exact system prompt used for the published Cell S
# run and is replayed rather than copied, so that any drift in the serving stack
# shows up as a difference against the published numbers.
PROMPTS = {
    "production": None,  # taken verbatim from each case's cached lea_log
    "paraphrase_a": (
        "/no_think\n"
        "You are a medical geneticist deciding which candidate gene explains a "
        "patient's presentation. For each candidate you are given a few passages "
        "from the published literature. Weigh the candidates against one another "
        "and decide whose evidence most specifically accounts for this particular "
        "combination of phenotypic features.\n\n"
        "Reply with one JSON ARRAY sorted from most to least likely. Every element "
        "must contain exactly these keys:\n"
        '  "gene" (string): the HGNC symbol, copied exactly as given.\n'
        '  "confidence" (float 0.0-1.0): how strongly you believe this gene is causal.\n'
        '  "rationale" (string, <=180 chars): a single sentence giving your reason.\n\n'
        "Exactly one candidate is causal, so the leading entry's confidence should "
        "stand well clear of the others. Every gene supplied must appear once and "
        "only once. Return the JSON array alone -- no markdown, no commentary."
    ),
    "paraphrase_b": (
        "/no_think\n"
        "Task: rank candidate genes by how well the supplied literature evidence "
        "supports each as the cause of the patient's phenotype.\n\n"
        "You will receive the patient's HPO terms followed by a block of evidence "
        "passages for each candidate gene. Compare candidates directly rather than "
        "judging each in isolation; the question is which single gene best explains "
        "the phenotype profile as a whole.\n\n"
        "Output format: a JSON ARRAY in descending order of confidence, each element "
        'having exactly the keys "gene" (HGNC symbol as provided), "confidence" '
        '(float between 0.0 and 1.0), and "rationale" (one sentence, at most 180 '
        "characters). Only one gene is causal, so the top confidence should be "
        "clearly separated from the remainder. Include each supplied gene exactly "
        "once. Emit the raw JSON array with no surrounding text."
    ),
}

GENE_RE = re.compile(r'"gene"\s*:\s*"([A-Za-z0-9\-_.]+)"')


def stratified_sample(n: int, seed: int = SEED) -> list:
    """MONDO-stratified subsample, balanced across the four categories."""
    rng = random.Random(seed)
    per = n // len(CATEGORIES)
    picked = []
    for cat in CATEGORIES:
        pool = sorted((c for c in load_cases() if c.category == cat), key=lambda c: c.case_id)
        picked.extend(rng.sample(pool, min(per, len(pool))))
    return sorted(picked, key=lambda c: c.case_id)


def parse_ranking(text: str, allowed: list[str]) -> list[str]:
    """Tolerant parse: JSON array first, regex over gene keys as a fallback.

    Mirrors the production parser so that a parse failure here means the same
    thing it meant in the original run.
    """
    allowed_set = set(allowed)
    txt = text.strip()
    # strip a markdown fence if the model added one despite instructions
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?", "", txt)
        txt = re.sub(r"\n?```$", "", txt).strip()
    start = txt.find("[")
    if start != -1:
        for end in range(len(txt), start, -1):
            frag = txt[start:end]
            try:
                arr = json.loads(frag)
            except json.JSONDecodeError:
                continue
            if isinstance(arr, list):
                out = []
                for e in arr:
                    if (
                        isinstance(e, dict)
                        and e.get("gene") in allowed_set
                        and e["gene"] not in out
                    ):
                        out.append(e["gene"])
                if out:
                    return out
            break
    out = []
    for g in GENE_RE.findall(txt):
        if g in allowed_set and g not in out:
            out.append(g)
    return out


def call_llm(system: str, user: str, timeout: int = 300) -> dict:
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 2048,
        "seed": SEED,
    }
    t0 = time.time()
    r = requests.post(VLLM_URL, json=body, timeout=timeout)
    r.raise_for_status()
    doc = r.json()
    return {
        "text": doc["choices"][0]["message"]["content"],
        "finish_reason": doc["choices"][0].get("finish_reason"),
        "latency_s": round(time.time() - t0, 3),
        "tokens_in": doc.get("usage", {}).get("prompt_tokens"),
        "tokens_out": doc.get("usage", {}).get("completion_tokens"),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    ap.add_argument("--variants", default="production,paraphrase_a,paraphrase_b")
    args = ap.parse_args()

    variants = [v for v in args.variants.split(",") if v]
    cases = stratified_sample(args.n)
    print(f"replaying LEA for {len(cases)} cases x {len(variants)} variants")

    published = load_ranks("S")
    absent_ids = {c.case_id for c in subset("overlap_absent")}

    results: dict[str, dict[str, dict]] = {v: {} for v in variants}

    for vi, variant in enumerate(variants, 1):
        vdir = OUT_RESP / variant
        vdir.mkdir(parents=True, exist_ok=True)
        t_start = time.time()
        for i, case in enumerate(cases, 1):
            cached = json.loads((RESP_DIR / f"{case.case_id}.json").read_text())
            log = cached["lea_log"]
            system = log["lea_system_prompt"] if variant == "production" else PROMPTS[variant]
            user = log["lea_user_prompt"]
            allowed = log["lea_top_gene_symbols"]

            out_path = vdir / f"{case.case_id}.json"
            if out_path.exists():
                rec = json.loads(out_path.read_text())
            else:
                try:
                    resp = call_llm(system, user)
                    order = parse_ranking(resp["text"], allowed)
                    rec = {
                        "case_id": case.case_id,
                        "variant": variant,
                        "category": case.category,
                        "causal_gene": case.causal_gene,
                        "n_candidates_to_lea": len(allowed),
                        "ranking": order,
                        "top1": order[0] if order else None,
                        "top1_correct": bool(order and order[0] == case.causal_gene),
                        "causal_rank": (
                            order.index(case.causal_gene) + 1 if case.causal_gene in order else None
                        ),
                        "parse_ok": bool(order),
                        "raw_text": resp["text"],
                        "finish_reason": resp["finish_reason"],
                        "latency_s": resp["latency_s"],
                        "tokens_in": resp["tokens_in"],
                        "tokens_out": resp["tokens_out"],
                    }
                except Exception as exc:
                    rec = {
                        "case_id": case.case_id,
                        "variant": variant,
                        "category": case.category,
                        "causal_gene": case.causal_gene,
                        "ranking": [],
                        "top1": None,
                        "top1_correct": False,
                        "causal_rank": None,
                        "parse_ok": False,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                out_path.write_text(json.dumps(rec, indent=1) + "\n")
            results[variant][case.case_id] = rec

            if i % 25 == 0 or i == len(cases):
                el = time.time() - t_start
                print(
                    f"  [{vi}/{len(variants)} {variant}] {i}/{len(cases)}  "
                    f"{el / i:.1f}s/case  eta {(len(cases) - i) * el / i / 60:.1f} min",
                    flush=True,
                )

    # ---------------- aggregate ----------------
    summary = []
    for variant in variants:
        recs = [results[variant][c.case_id] for c in cases]
        fair = [r for r in recs if r["case_id"] in absent_ids]

        def acc(rs):
            return round(float(np.mean([bool(r["top1_correct"]) for r in rs])), 4) if rs else None

        n_err = sum(1 for r in recs if not r.get("parse_ok"))
        summary.append(
            {
                "variant": variant,
                "n": len(recs),
                "n_parse_failures": n_err,
                "top1_overall": acc(recs),
                "n_fair": len(fair),
                "top1_overlap_absent": acc(fair),
                "mean_latency_s": round(
                    float(np.mean([r.get("latency_s", np.nan) for r in recs])), 2
                ),
            }
        )

    # agreement of each variant with the published Cell S run on this subsample
    pub = {
        c.case_id: int(published[c.case_id] is not None and published[c.case_id] <= 1)
        for c in cases
    }
    agreement = []
    for variant in variants:
        same = sum(
            1 for c in cases if int(results[variant][c.case_id]["top1_correct"]) == pub[c.case_id]
        )
        agreement.append(
            {
                "variant": variant,
                "agreement_with_published_cell_S": round(same / len(cases), 4),
                "published_top1_on_subsample": round(float(np.mean(list(pub.values()))), 4),
            }
        )

    spread = [s["top1_overall"] for s in summary if s["top1_overall"] is not None]
    fair_spread = [
        s["top1_overlap_absent"] for s in summary if s["top1_overlap_absent"] is not None
    ]

    payload = {
        "work_package": "WP8-D",
        "description": (
            "Prompt-sensitivity replay of the LEA stage over cached retrieval. "
            "Only the instruction wording changes; evidence, candidates and "
            "decoding are held identical."
        ),
        "seed": SEED,
        "model": MODEL,
        "decoding": {"temperature": 0.0, "top_p": 1.0, "seed": SEED},
        "sampling_frame": "MONDO-stratified subsample, seed 42",
        "n_cases": len(cases),
        "variants": summary,
        "agreement": agreement,
        "range_top1_overall_pp": round((max(spread) - min(spread)) * 100, 1) if spread else None,
        "range_top1_overlap_absent_pp": (
            round((max(fair_spread) - min(fair_spread)) * 100, 1) if fair_spread else None
        ),
        "prompts": {
            k: (v if v else "<verbatim production prompt from lea_log>") for k, v in PROMPTS.items()
        },
    }
    p = write_json("wp8d_prompt_sensitivity.json", payload)
    print(f"\nwrote {p}")
    for s in summary:
        print(
            f"  {s['variant']:<14} overall {s['top1_overall']}  "
            f"overlap-absent {s['top1_overlap_absent']} (n={s['n_fair']})  "
            f"parse-fail {s['n_parse_failures']}"
        )
    print(
        f"  range overall: {payload['range_top1_overall_pp']} pp; "
        f"overlap-absent: {payload['range_top1_overlap_absent_pp']} pp"
    )


if __name__ == "__main__":
    main()
