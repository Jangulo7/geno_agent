"""LIRICAL HPO-only baseline runner (Cell M, paper extension v3).

This module wraps the LIRICAL CLI (Java) to produce a ranked list of
candidate genes from HPO terms alone. LIRICAL ranks *diseases*, not
genes, so the runner additionally maps disease IDs (OMIM/MONDO/ORPHA)
to gene symbols via three lookups:

  1. ``mim2gene_medgen`` (NCBI) — OMIM phenotype/gene → NCBI gene ID
  2. ``en_product6.xml`` (Orphanet) — Orphanet disease → gene symbol
  3. ``hgnc_complete_set_2026-04-07.txt`` (HGNC) — NCBI gene ID + symbol normalization

For each of the case's 50 candidate genes, the runner takes the best
(max posttest probability) ranked disease that maps to that gene and
uses that rank. Candidates with no matching disease in LIRICAL's output
fall to rank 51+ in their input order.

LIRICAL CLI distribution and data dir live OUTSIDE the git repo:
  ~/rare-disease-rag/lirical/dist/lirical-cli-2.4.0/lirical-cli-2.4.0.jar
  ~/rare-disease-rag/lirical/data/   (hp.json, phenotype.hpoa, mim2gene_medgen, en_product6.xml, hgnc_complete_set.txt)

References:
  - LIRICAL paper: Robinson et al. 2020, AJHG (PMID 32755546)
  - LIRICAL v2.4.0: https://github.com/TheJacksonLaboratory/LIRICAL
  - Paper extension plan v3: reports/paper_extension_plan_v3.md
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

_DEFAULT_LIRICAL_HOME: Final[Path] = Path.home() / "rare-disease-rag" / "lirical"
_DEFAULT_JAR_NAME: Final[str] = "lirical-cli-2.4.0.jar"
_HGNC_FALLBACK: Final[Path] = (
    Path(__file__).resolve().parents[2] / "data" / "HGNC" / "hgnc_complete_set.txt"
)


@dataclass(frozen=True)
class LiricalPaths:
    """Resolved paths to the LIRICAL CLI jar + data directory."""

    jar: Path
    data_dir: Path
    work_dir: Path

    @classmethod
    def from_default(cls, home: Path = _DEFAULT_LIRICAL_HOME) -> LiricalPaths:
        """Resolve paths assuming the standard install layout."""
        return cls(
            jar=home / "dist" / "lirical-cli-2.4.0" / _DEFAULT_JAR_NAME,
            data_dir=home / "data",
            work_dir=home / "results",
        )

    def assert_present(self) -> None:
        """Raise FileNotFoundError if any required path is missing."""
        if not self.jar.is_file():
            raise FileNotFoundError(f"LIRICAL jar not found at {self.jar}")
        if not self.data_dir.is_dir():
            raise FileNotFoundError(f"LIRICAL data dir not found at {self.data_dir}")
        for name in ("hp.json", "phenotype.hpoa", "mim2gene_medgen", "en_product6.xml"):
            p = self.data_dir / name
            if not p.is_file():
                raise FileNotFoundError(f"LIRICAL data file missing: {p}")
        self.work_dir.mkdir(parents=True, exist_ok=True)


# ============================================================================
# Disease -> Gene mapping
# ============================================================================


def _build_omim_to_genes(mim2gene_medgen: Path, hgnc_complete: Path) -> dict[str, set[str]]:
    """Build ``OMIM:<id> -> {hgnc_symbol, ...}`` from NCBI mim2gene_medgen.

    The mim2gene_medgen file has columns:
        #MIM number, GeneID, type, Source, MedGenCUI, Comment

    For each MIM that maps to one or more NCBI Gene IDs (type == 'gene' or
    rows where GeneID is not '-'), look up the gene's HGNC primary symbol.

    Args:
        mim2gene_medgen: NCBI mim2gene_medgen TSV (LIRICAL data dir).
        hgnc_complete: hgnc_complete_set.txt with NCBI Gene ID column.

    Returns:
        Dict from ``"OMIM:<n>"`` to set of HGNC primary symbols.
    """
    # NCBI gene id -> HGNC primary symbol
    ncbi_to_symbol: dict[str, str] = {}
    with hgnc_complete.open() as f:
        header = next(f).rstrip("\n").split("\t")
        try:
            i_sym = header.index("symbol")
            i_ncbi = header.index("entrez_id")
        except ValueError as e:
            raise ValueError(f"HGNC TSV missing expected columns: {e}") from e
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) <= max(i_sym, i_ncbi):
                continue
            sym = parts[i_sym].strip()
            ncbi = parts[i_ncbi].strip()
            if sym and ncbi:
                ncbi_to_symbol[ncbi] = sym

    omim_to_genes: dict[str, set[str]] = {}
    with mim2gene_medgen.open() as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            mim = parts[0].strip()
            gene_id = parts[1].strip()
            if not mim or gene_id == "-":
                continue
            sym_opt = ncbi_to_symbol.get(gene_id)
            if sym_opt:
                omim_to_genes.setdefault(f"OMIM:{mim}", set()).add(sym_opt)
    return omim_to_genes


def _build_orpha_to_genes(en_product6: Path) -> dict[str, set[str]]:
    """Build ``ORPHA:<id> -> {hgnc_symbol, ...}`` from Orphanet en_product6.xml.

    The Orphanet en_product6.xml schema groups <Disorder> elements, each
    with an OrphaCode and a <DisorderGeneAssociationList> containing
    <DisorderGeneAssociation><Gene><Symbol>...</Symbol></Gene>...

    Args:
        en_product6: Orphanet XML in LIRICAL data dir.

    Returns:
        Dict from ``"ORPHA:<n>"`` to set of gene symbols.
    """
    orpha_to_genes: dict[str, set[str]] = {}
    tree = ET.parse(en_product6)
    root = tree.getroot()
    for disorder in root.iter("Disorder"):
        orpha_code_el = disorder.find("OrphaCode")
        if orpha_code_el is None or not orpha_code_el.text:
            continue
        orpha_id = f"ORPHA:{orpha_code_el.text.strip()}"
        for gene_assoc in disorder.iter("DisorderGeneAssociation"):
            gene_el = gene_assoc.find("Gene")
            if gene_el is None:
                continue
            sym_el = gene_el.find("Symbol")
            if sym_el is not None and sym_el.text:
                orpha_to_genes.setdefault(orpha_id, set()).add(sym_el.text.strip())
    return orpha_to_genes


def load_disease_to_genes(paths: LiricalPaths) -> dict[str, set[str]]:
    """Build a unified ``disease_id -> {hgnc_symbol, ...}`` lookup.

    Sources:
        - OMIM: mim2gene_medgen (LIRICAL data dir) + HGNC for symbol resolution
        - ORPHA: en_product6.xml (LIRICAL data dir)
        - MONDO: not directly supported by LIRICAL data; LIRICAL outputs
          OMIM and ORPHA disease IDs, not MONDO.

    Args:
        paths: Resolved :class:`LiricalPaths`.

    Returns:
        Single dict merging OMIM and ORPHA mappings.
    """
    hgnc = paths.data_dir / "hgnc_complete_set.txt"
    if not hgnc.is_file():
        # Fall back to project-pinned HGNC (2026-04-07)
        hgnc = _HGNC_FALLBACK
    logger.info("Loading OMIM->gene from %s", paths.data_dir / "mim2gene_medgen")
    omim = _build_omim_to_genes(paths.data_dir / "mim2gene_medgen", hgnc)
    logger.info("Loading ORPHA->gene from %s", paths.data_dir / "en_product6.xml")
    orpha = _build_orpha_to_genes(paths.data_dir / "en_product6.xml")
    merged: dict[str, set[str]] = {}
    merged.update(omim)
    for k, v in orpha.items():
        merged[k] = v
    logger.info(
        "Disease->gene lookup built: %d OMIM, %d ORPHA, %d total",
        len(omim),
        len(orpha),
        len(merged),
    )
    return merged


# ============================================================================
# LIRICAL output parsing
# ============================================================================


def _parse_lirical_json(json_path: Path) -> list[tuple[str, float]]:
    """Parse LIRICAL JSON output → list of (disease_id, posttest_probability).

    LIRICAL v2.x JSON schema:
        {
          "analysisData": {...},
          "analysisMetadata": {...},
          "analysisResults": [
            {
              "diseaseId": "OMIM:619340",
              "pretestProbability": 1.4e-4,
              "posttestProbability": 0.97,
              "compositeLR": 1234.5,
              ...
            },
            ...
          ]
        }

    Args:
        json_path: Path to the LIRICAL JSON output file.

    Returns:
        List of (disease_id, posttest_probability) tuples sorted by
        posttest_probability descending (LIRICAL's native rank order).
    """
    with json_path.open() as f:
        doc = json.load(f)
    results = doc.get("analysisResults", [])
    parsed: list[tuple[str, float]] = []
    for r in results:
        did = r.get("diseaseId") or r.get("diseaseCurie")
        if not did:
            continue
        post = r.get("posttestProbability", 0.0)
        try:
            post_f = float(post)
        except (TypeError, ValueError):
            post_f = 0.0
        parsed.append((did, post_f))
    parsed.sort(key=lambda x: -x[1])
    return parsed


def _payload_from_diseases(
    case: dict,
    ranked_diseases: list[tuple[str, float]],
    disease_to_genes: dict[str, set[str]],
) -> list[dict]:
    """Build the cells-compatible JSON payload from LIRICAL disease rankings.

    For each candidate gene in ``case["candidate_genes"]``:
        1. Find all diseases in ``ranked_diseases`` that map to this gene.
        2. Take the highest posttest probability across those diseases.
        3. Rank candidates by their best score; candidates with no
           matching disease land last in their input order.

    Args:
        case: Phase 1B test case dict.
        ranked_diseases: Output of :func:`_parse_lirical_json`.
        disease_to_genes: Output of :func:`load_disease_to_genes`.

    Returns:
        List of ``{symbol, is_causal, aggregate_confidence,
        supporting_chunks, final_rank}`` dicts.
    """
    # Build gene_symbol -> best posttest probability across all diseases
    # that map to this gene.
    gene_best_score: dict[str, float] = {}
    for did, post in ranked_diseases:
        genes = disease_to_genes.get(did, set())
        for g in genes:
            prev = gene_best_score.get(g, 0.0)
            if post > prev:
                gene_best_score[g] = post

    candidate_genes: list[str] = list(case["candidate_genes"])
    causal_gene: str = case["causal_gene"]

    # Sort candidates by their best score (descending), then by input
    # order to keep ties stable.
    ordered = sorted(
        enumerate(candidate_genes),
        key=lambda iv: (-gene_best_score.get(iv[1], 0.0), iv[0]),
    )

    payload: list[dict] = []
    for rank, (_, symbol) in enumerate(ordered, start=1):
        payload.append(
            {
                "symbol": symbol,
                "is_causal": symbol == causal_gene,
                "aggregate_confidence": gene_best_score.get(symbol, 0.0),
                "supporting_chunks": [],
                "final_rank": rank,
            }
        )
    return payload


# ============================================================================
# LIRICAL invocation
# ============================================================================


class LiricalRunner:
    """Wrap the LIRICAL CLI for HPO-only batch evaluation (Cell M).

    Each ``run_case`` call spawns one JVM and runs LIRICAL on a single
    case via ``lirical prioritize --observed-phenotypes HP:...``. The
    disease ranking is then mapped back to gene rankings for the case's
    50 candidate genes.

    Args:
        paths: Resolved :class:`LiricalPaths`.
        disease_to_genes: Optional pre-loaded ``disease_id -> {gene_symbol}``
            map. If omitted, loaded fresh on first ``run_case``.
        java_xmx: JVM heap cap (default 8 GB — matches LIRICAL guidance).
    """

    def __init__(
        self,
        paths: LiricalPaths,
        *,
        disease_to_genes: dict[str, set[str]] | None = None,
        java_xmx: str = "8g",
    ) -> None:
        paths.assert_present()
        self.paths = paths
        self.java_xmx = java_xmx
        self._disease_to_genes = disease_to_genes

    @classmethod
    def from_default(cls) -> LiricalRunner:
        """Resolve standard paths + return a configured runner."""
        return cls(LiricalPaths.from_default())

    @property
    def disease_to_genes(self) -> dict[str, set[str]]:
        """Lazy-loaded disease -> gene-symbol lookup."""
        if self._disease_to_genes is None:
            self._disease_to_genes = load_disease_to_genes(self.paths)
        return self._disease_to_genes

    def run_case(self, case: dict, *, timeout: int = 180) -> list[dict]:
        """Run LIRICAL HPO-only for one case and return ranked payload.

        Args:
            case: Phase 1B test case dict with ``hpo_terms``,
                ``candidate_genes``, ``causal_gene``.
            timeout: Subprocess timeout in seconds. LIRICAL HPO-only
                typically completes in 15-60 s; 3 minutes is generous.

        Returns:
            Cells-compatible JSON payload (see
            :func:`_payload_from_diseases`).
        """
        case_id_safe = re.sub(r"[^A-Za-z0-9._-]", "_", case["case_id"])
        with tempfile.TemporaryDirectory(
            prefix=f"lirical_{case_id_safe}_", dir=self.paths.work_dir
        ) as tmp:
            tmp_path = Path(tmp)
            hpo_csv = ",".join(case["hpo_terms"])
            output_prefix = f"case_{case_id_safe}"

            # -m 100000: emit up to 100k diseases (covers full ~14k OMIM
            # + Orphanet set). LIRICAL forbids combining -m with -t, so
            # we use -m alone for completeness.
            # --use-orphanet: include Orphanet diseases (off by default).
            # -x: output file prefix.
            cmd = [
                "java",
                f"-Xmx{self.java_xmx}",
                "-jar",
                str(self.paths.jar),
                "prioritize",
                "-p",
                hpo_csv,
                "-d",
                str(self.paths.data_dir),
                "-m",
                "100000",
                "--use-orphanet",
                "-f",
                "json",
                "-o",
                str(tmp_path),
                "-x",
                output_prefix,
            ]
            logger.debug("Running LIRICAL: %s", " ".join(cmd))
            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            json_candidates = list(tmp_path.glob(f"{output_prefix}*.json"))
            if not json_candidates:
                raise FileNotFoundError(f"LIRICAL produced no JSON for case {case['case_id']}")
            ranked = _parse_lirical_json(json_candidates[0])
            return _payload_from_diseases(case, ranked, self.disease_to_genes)


def run_one_case_to_json(
    case: dict,
    output_dir: Path,
    *,
    runner: LiricalRunner | None = None,
    overwrite: bool = False,
) -> Path:
    """Run one case and persist the cell_M JSON to disk.

    Args:
        case: Phase 1B test case dict.
        output_dir: ``data/eval_1050/cell_M_lirical_hpo_only/`` directory.
        runner: Reusable :class:`LiricalRunner`; one is constructed
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
    runner = runner or LiricalRunner.from_default()
    payload = runner.run_case(case)
    with out_path.open("w") as f:
        json.dump(payload, f, indent=2)
    return out_path
