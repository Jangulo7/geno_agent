"""Exomiser HPO-only baseline runner (Cell K, master plan §11.5).

This module wraps the Exomiser CLI to produce a ranked list of candidate
genes from HPO terms alone — no VCF, no variant data. See
`MASTER_PROJECT_v2.1.md` §11.5 and `reports/research_summary_15052026.md` §2
for the rationale (apples-to-apples comparison with geno_agent's
phenotype-only input).

Pipeline per case:
  1. Build a Phenopacket job YAML (HPO terms + hiPhivePrioritiser).
  2. Invoke Exomiser CLI via subprocess.
  3. Parse the TSV_GENE output (ranked genes for ALL human genes by
     phenotype similarity).
  4. Filter to the case's 50 candidate genes; preserve relative rank.
  5. Emit a JSON payload in the same shape as cells A-J for the
     existing aggregator.

The Exomiser CLI distribution and phenotype data live OUTSIDE the git
repo per the master plan's "Heavy persistent artifacts" rule — under
``~/rare-disease-rag/exomiser/``.
"""

from __future__ import annotations

import csv
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import yaml

logger = logging.getLogger(__name__)

# Default Exomiser install layout (master plan §3 "outside the repo").
_DEFAULT_EXOMISER_HOME: Final[Path] = Path.home() / "rare-disease-rag" / "exomiser"
_DEFAULT_JAR_NAME: Final[str] = "exomiser-cli-14.0.2.jar"
_DEFAULT_DATA_VERSION: Final[str] = "2402"


@dataclass(frozen=True)
class ExomiserPaths:
    """Resolved paths to the Exomiser CLI jar + data directory."""

    jar: Path
    data_dir: Path
    work_dir: Path

    @classmethod
    def from_default(cls, home: Path = _DEFAULT_EXOMISER_HOME) -> ExomiserPaths:
        """Resolve paths assuming the standard install layout."""
        return cls(
            jar=home / "application" / "exomiser-cli-14.0.2" / _DEFAULT_JAR_NAME,
            data_dir=home / "data",
            work_dir=home / "results",
        )

    def assert_present(self) -> None:
        """Raise FileNotFoundError if any required path is missing."""
        if not self.jar.is_file():
            raise FileNotFoundError(f"Exomiser jar not found at {self.jar}")
        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"Exomiser data dir not found at {self.data_dir}")
        self.work_dir.mkdir(parents=True, exist_ok=True)


def _build_phenopacket(case: dict) -> dict:
    """Build a v1 Phenopacket from a Phase 1B test case dict.

    The Phenopacket carries only the HPO terms; no ``htsFiles`` is
    attached, which triggers Exomiser's phenotype-only analysis path.

    Args:
        case: One row from ``data/test_cases/test_cases.jsonl``.

    Returns:
        Dict matching the v1 Phenopacket schema accepted by Exomiser 14.x.
    """
    return {
        "id": case["case_id"],
        "subject": {"id": case["case_id"]},
        "phenotypicFeatures": [
            {"type": {"id": hpo_id, "label": hpo_id}} for hpo_id in case["hpo_terms"]
        ],
        "metaData": {
            "created": "2026-05-15T00:00:00Z",
            "createdBy": "geno_agent_cell_K",
            "resources": [
                {
                    "id": "hp",
                    "name": "human phenotype ontology",
                    "url": "http://purl.obolibrary.org/obo/hp.owl",
                    "version": "hp/releases/2026-02-16",
                    "namespacePrefix": "HP",
                    "iriPrefix": "http://purl.obolibrary.org/obo/HP_",
                },
            ],
            "phenopacketSchemaVersion": "1.0",
        },
    }


def _write_sample_yaml(phenopacket: dict, sample_path: Path) -> None:
    """Write the Phenopacket as a standalone --sample YAML file.

    Exomiser 14.x's ``--preset phenotype-only`` flow takes the
    Phenopacket directly via ``--sample``; no separate analysis YAML
    is needed because the preset embeds the prioritiser stack.
    """
    with sample_path.open("w") as f:
        yaml.safe_dump(phenopacket, f, sort_keys=False)


def _parse_tsv_gene(tsv_path: Path) -> list[tuple[str, float]]:
    """Parse Exomiser's TSV_GENE output into (symbol, score) tuples.

    Exomiser 14.x TSV_GENE columns include ``#GENE_SYMBOL`` and
    ``EXOMISER_GENE_PHENO_SCORE``. Ranks are implicit from row order.

    Args:
        tsv_path: Path to ``<output_filename>.genes.tsv``.

    Returns:
        List of ``(gene_symbol, phenotype_score)`` in Exomiser's rank
        order (highest score first).
    """
    with tsv_path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = []
        for row in reader:
            symbol = row.get("#GENE_SYMBOL") or row.get("GENE_SYMBOL")
            score_str = (
                row.get("EXOMISER_GENE_PHENO_SCORE")
                or row.get("PHENO_SCORE")
                or row.get("EXOMISER_GENE_COMBINED_SCORE")
                or "0"
            )
            try:
                score = float(score_str)
            except ValueError:
                score = 0.0
            if symbol:
                rows.append((symbol, score))
    return rows


def _payload_from_ranked(case: dict, ranked_all_genes: list[tuple[str, float]]) -> list[dict]:
    """Build the cells-compatible JSON payload from Exomiser output.

    The returned payload has one entry per candidate gene in the case,
    sorted by Exomiser's phenotype score (highest first). Genes that
    Exomiser did not score get score 0.0 and land after the scored
    candidates in their input order.

    Args:
        case: Phase 1B test case dict with ``candidate_genes`` and
            ``causal_gene``.
        ranked_all_genes: ``(symbol, score)`` from
            :func:`_parse_tsv_gene` for ALL human genes.

    Returns:
        List of ``{symbol, is_causal, aggregate_confidence,
        supporting_chunks, final_rank}`` dicts matching the cells A-J
        format consumed by ``scripts/eval/aggregate_metrics.py``.
    """
    score_by_symbol: dict[str, float] = dict(ranked_all_genes)
    candidate_genes: list[str] = list(case["candidate_genes"])
    causal_gene: str = case["causal_gene"]

    scored = sorted(
        candidate_genes,
        key=lambda g: (-score_by_symbol.get(g, 0.0), g),
    )

    payload: list[dict] = []
    for rank, symbol in enumerate(scored, start=1):
        payload.append(
            {
                "symbol": symbol,
                "is_causal": symbol == causal_gene,
                "aggregate_confidence": score_by_symbol.get(symbol, 0.0),
                "supporting_chunks": [],
                "final_rank": rank,
            }
        )
    return payload


class ExomiserRunner:
    """Wrap the Exomiser CLI for HPO-only batch evaluation.

    One instance corresponds to one Exomiser install. ``run_case`` is
    re-entrant and writes per-case scratch files under a unique
    temp directory.

    Typical use:

    >>> runner = ExomiserRunner.from_default()
    >>> payload = runner.run_case(case_dict)
    >>> # payload is the same shape as a cell_*/case.json file

    Args:
        paths: Resolved :class:`ExomiserPaths`.
        java_xmx: JVM heap cap. Default ``"4g"`` is enough for hiPhive
            on a single phenopacket; HPO-only analysis is not
            memory-hungry.
    """

    def __init__(self, paths: ExomiserPaths, *, java_xmx: str = "4g") -> None:
        paths.assert_present()
        self.paths = paths
        self.java_xmx = java_xmx

    @classmethod
    def from_default(cls) -> ExomiserRunner:
        """Resolve standard paths + return a configured runner."""
        return cls(ExomiserPaths.from_default())

    def run_case(self, case: dict, *, timeout: int = 300) -> list[dict]:
        """Run Exomiser HPO-only for one case and return ranked payload.

        Args:
            case: Phase 1B test case dict (see
                ``data/test_cases/test_cases.jsonl``).
            timeout: Subprocess timeout in seconds. HPO-only analysis
                typically completes in 5-15 s; 5 minutes is generous.

        Returns:
            Cells-compatible JSON payload (see
            :func:`_payload_from_ranked`).

        Raises:
            subprocess.CalledProcessError: If Exomiser exits non-zero.
            FileNotFoundError: If the expected TSV_GENE output is missing.
        """
        case_id_safe = case["case_id"].replace(":", "_").replace("/", "_")
        with tempfile.TemporaryDirectory(
            prefix=f"exomiser_{case_id_safe}_", dir=self.paths.work_dir
        ) as tmp:
            tmp_path = Path(tmp)
            sample_path = tmp_path / "sample.yml"
            output_prefix = f"case_{case_id_safe}"

            phenopacket = _build_phenopacket(case)
            _write_sample_yaml(phenopacket, sample_path)

            # --preset phenotype-only triggers Exomiser's bundled
            # hiPhive-only stack. Spring Boot finds application.properties
            # via cwd (set below) — passing --spring.config.location
            # explicitly conflicts with Exomiser's option parser, which
            # treats the next arg as the --output-format value.
            cmd = [
                "java",
                f"-Xmx{self.java_xmx}",
                "-jar",
                str(self.paths.jar),
                "--sample",
                str(sample_path),
                "--preset",
                "phenotype-only",
                "--output-directory",
                str(tmp_path),
                "--output-filename",
                output_prefix,
                "--output-format",
                "TSV_GENE,JSON",
            ]
            logger.debug("Running exomiser: %s", " ".join(cmd))
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.paths.jar.parent),
            )

            tsv_candidates = list(tmp_path.glob(f"{output_prefix}*.genes.tsv"))
            if not tsv_candidates:
                raise FileNotFoundError(
                    f"Exomiser produced no .genes.tsv for case {case['case_id']}"
                )
            tsv_path = tsv_candidates[0]
            ranked_all = _parse_tsv_gene(tsv_path)
            return _payload_from_ranked(case, ranked_all)


def run_one_case_to_json(
    case: dict,
    output_dir: Path,
    *,
    runner: ExomiserRunner | None = None,
    overwrite: bool = False,
) -> Path:
    """Run one case and persist the cell_K JSON to disk.

    Args:
        case: Phase 1B test case dict.
        output_dir: ``data/eval/cell_K_*/`` directory.
        runner: Reusable :class:`ExomiserRunner`; one is constructed
            on the fly if omitted.
        overwrite: If False, skip cases whose output JSON already exists.

    Returns:
        Path to the written JSON file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{case['case_id']}.json"
    if out_path.is_file() and not overwrite:
        logger.info("skip %s (already exists)", case["case_id"])
        return out_path
    runner = runner or ExomiserRunner.from_default()
    payload = runner.run_case(case)
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2)
    return out_path
