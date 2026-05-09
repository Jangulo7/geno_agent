"""Ingest GA4GH Phenopacket-Store v0.1.19 into a single normalized JSONL.

Implements master plan §6 step 1 (Phase 1B / §7 step [9]). Reads every
``*.json`` file recursively under ``$PHENOPACKET_DIR/v$PHENOPACKET_STORE_VERSION/``
and emits one JSONL record per phenopacket with the four field families that
the rest of Phase 1B (steps 2-6) depends on:

  * ``case_id``        — ``"<cohort>:<file_stem>"`` (from parent directory name + file basename)
  * ``source_path``    — path to the source JSON, repo-relative
  * ``subject_id``     — ``subject.id`` from the phenopacket
  * ``hpo_terms``      — observed (not excluded) HPO term IDs, deduplicated, order preserved
  * ``diseases``       — list of ``{"id": "OMIM:...", "label": "..."}``
  * ``interpretations``— causal genomic interpretations with ``gene_symbol`` /
                         ``hgnc_id`` / ``variant`` / ``ascertained`` flags

Run from the project root::

    source /home/hana77/pytorch-env/bin/activate
    python scripts/cases/13_load_phenopackets.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils.seed import apply_seeds  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")
apply_seeds()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("load_phenopackets")

EXPECTED_COUNT_LO: Final[int] = 6000
EXPECTED_COUNT_HI: Final[int] = 7500
EXPECTED_COUNT_NOMINAL: Final[int] = 6668  # master plan §3.4


def extract_hpo_terms(pp: dict) -> list[str]:
    """Return only observed (non-excluded) HPO term IDs, deduplicated.

    Args:
        pp: One phenopacket dict (parsed from JSON).

    Returns:
        List of HP IDs (e.g., ``"HP:0001250"``) in original document order
        with duplicates removed. Empty list if no observed phenotypes.
    """
    out: list[str] = []
    for pf in pp.get("phenotypicFeatures", []):
        if pf.get("excluded"):
            continue
        type_ = pf.get("type") or {}
        tid = type_.get("id")
        if tid and tid.startswith("HP:"):
            out.append(tid)
    seen: set[str] = set()
    deduped: list[str] = []
    for t in out:
        if t not in seen:
            deduped.append(t)
            seen.add(t)
    return deduped


def extract_diseases(pp: dict) -> list[dict]:
    """Return non-excluded disease records as ``{id, label}`` dicts."""
    out: list[dict] = []
    for d in pp.get("diseases", []):
        if d.get("excluded"):
            continue
        term = d.get("term") or {}
        out.append({"id": term.get("id"), "label": term.get("label")})
    return out


def extract_interpretations(pp: dict) -> list[dict]:
    """Walk ``interpretations[].diagnosis.genomicInterpretations[]``.

    Phenopacket schema v2 nests genomic interpretations:

        interpretations[].diagnosis.genomicInterpretations[].variantInterpretation
            .variationDescriptor.geneContext  -> {symbol, valueId (HGNC:...)}

    Args:
        pp: Parsed phenopacket dict.

    Returns:
        List of dicts ``{gene_symbol, hgnc_id, variant, ascertained}``.
        ``ascertained`` is True when the interpretation status is
        ``CAUSATIVE``, ``CONTRIBUTORY``, or unspecified (the default in
        many phenopackets).
    """
    out: list[dict] = []
    for interp in pp.get("interpretations", []):
        diag = interp.get("diagnosis") or {}
        for gi in diag.get("genomicInterpretations", []):
            status = gi.get("interpretationStatus", "") or ""
            vi = gi.get("variantInterpretation") or {}
            vd = vi.get("variationDescriptor") or {}
            gc = vd.get("geneContext") or {}
            symbol = gc.get("symbol")
            value_id = gc.get("valueId") or ""
            if symbol:
                out.append(
                    {
                        "gene_symbol": symbol,
                        "hgnc_id": value_id if value_id.startswith("HGNC:") else None,
                        "variant": vd.get("label") or vd.get("id", ""),
                        "ascertained": status in ("CAUSATIVE", "CONTRIBUTORY", ""),
                    }
                )
    return out


def parse_args() -> argparse.Namespace:
    """CLI args."""
    version = os.environ.get("PHENOPACKET_STORE_VERSION", "0.1.19")
    pp_dir = os.environ.get("PHENOPACKET_DIR", str(PROJECT_ROOT / "data" / "phenopackets"))
    tc_dir = os.environ.get("TEST_CASES_DIR", str(PROJECT_ROOT / "data" / "test_cases"))
    p = argparse.ArgumentParser(description="Ingest Phenopacket-Store JSONs to JSONL.")
    p.add_argument(
        "--input-dir",
        type=Path,
        default=Path(pp_dir) / f"v{version}",
        help="Directory holding the extracted phenopackets (default: $PHENOPACKET_DIR/v$PHENOPACKET_STORE_VERSION)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path(tc_dir) / "01_all_phenopackets.jsonl",
        help="Output JSONL path (default: $TEST_CASES_DIR/01_all_phenopackets.jsonl)",
    )
    return p.parse_args()


def main() -> int:
    """Read every phenopacket JSON under input-dir, emit normalized JSONL."""
    args = parse_args()
    if not args.input_dir.exists():
        logger.error(f"Input dir not found: {args.input_dir}")
        logger.error("Did §7 step [8] (04_download_phenopacket_store.sh) run successfully?")
        return 1

    json_files = sorted(args.input_dir.rglob("*.json"))
    if not json_files:
        logger.error(f"No *.json files under {args.input_dir}")
        return 1
    logger.info(f"Found {len(json_files):,} phenopacket JSON files under {args.input_dir}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    n_seen = n_written = n_skipped = 0
    n_with_hpo = n_with_disease = n_with_interp = 0
    hpo_count_total = interp_count_total = 0

    with args.output.open("w", encoding="utf-8") as fout:
        for jf in tqdm(json_files, desc="loading"):
            n_seen += 1
            try:
                pp = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"  parse error in {jf.name}: {exc}")
                n_skipped += 1
                continue

            cohort = jf.parent.name
            case_id = f"{cohort}:{jf.stem}"
            hpo = extract_hpo_terms(pp)
            diseases = extract_diseases(pp)
            interps = extract_interpretations(pp)

            record = {
                "case_id": case_id,
                "source_path": str(jf.relative_to(PROJECT_ROOT)),
                "subject_id": (pp.get("subject") or {}).get("id"),
                "hpo_terms": hpo,
                "diseases": diseases,
                "interpretations": interps,
            }
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_written += 1
            n_with_hpo += int(bool(hpo))
            n_with_disease += int(bool(diseases))
            n_with_interp += int(bool(interps))
            hpo_count_total += len(hpo)
            interp_count_total += len(interps)

    logger.info("=== Ingest summary ===")
    logger.info(f"  files seen:           {n_seen:,}")
    logger.info(f"  records written:      {n_written:,}")
    logger.info(f"  parse errors skipped: {n_skipped:,}")
    logger.info(
        f"  with >= 1 HPO term:   {n_with_hpo:,} ({100 * n_with_hpo / max(n_written, 1):.1f}%)"
    )
    logger.info(
        f"  with >= 1 disease:    {n_with_disease:,} ({100 * n_with_disease / max(n_written, 1):.1f}%)"
    )
    logger.info(
        f"  with >= 1 interp:     {n_with_interp:,} ({100 * n_with_interp / max(n_written, 1):.1f}%)"
    )
    logger.info(f"  avg HPO terms/case:   {hpo_count_total / max(n_written, 1):.1f}")
    logger.info(f"  avg interps/case:     {interp_count_total / max(n_written, 1):.2f}")
    logger.info(f"  output:               {args.output}")

    if not (EXPECTED_COUNT_LO <= n_written <= EXPECTED_COUNT_HI):
        logger.warning(
            f"Record count {n_written} is far from master plan §3.4's "
            f"expected ~{EXPECTED_COUNT_NOMINAL}; investigate."
        )
    return 0 if n_written else 1


if __name__ == "__main__":
    raise SystemExit(main())
