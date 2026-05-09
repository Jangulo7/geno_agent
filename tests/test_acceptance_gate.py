"""Tests for the Phase 1B acceptance gate (B9 / scripts/cases/20_validate_test_cases.py).

Each of the 5 master-plan §4.11.5 checks gets a unit test covering:
  * the pass case
  * one or more clearly-engineered failure cases

Aggregation of all checks is also tested via ``run_all_checks``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_gate_module():
    """Load ``20_validate_test_cases.py`` by file path."""
    path = PROJECT_ROOT / "scripts" / "cases" / "20_validate_test_cases.py"
    spec = importlib.util.spec_from_file_location("gate_module", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["gate_module"] = module
    spec.loader.exec_module(module)
    return module


def _good_case(
    case_id: str = "c-001",
    causal: str = "BRCA1",
    category: str = "neurological",
    pmc: int = 10,
) -> dict:
    """A case that should pass every check."""
    return {
        "case_id": case_id,
        "category": category,
        "hpo_terms": ["HP:0001250", "HP:0001263", "HP:0002650"],
        "diseases": [{"id": "OMIM:154700", "label": "..."}],
        "causal_gene": causal,
        "candidate_genes": [causal] + [f"GENE{i:04d}" for i in range(49)],
        "causal_gene_index_in_candidates": 0,
        "pmc_article_count": pmc,
        "source_phenopacket": "data/phenopackets/v0.1.19/.../foo.json",
    }


class TestCheckHpoTerms:
    def test_pass(self) -> None:
        gate = _load_gate_module()
        assert gate.check_hpo_terms(_good_case(), min_hpo=3) == []

    def test_fail_too_few(self) -> None:
        gate = _load_gate_module()
        case = _good_case()
        case["hpo_terms"] = ["HP:0001250"]
        out = gate.check_hpo_terms(case, min_hpo=3)
        assert len(out) == 1 and "only 1" in out[0]

    def test_fail_missing_field(self) -> None:
        gate = _load_gate_module()
        case = _good_case()
        case.pop("hpo_terms")
        out = gate.check_hpo_terms(case, min_hpo=3)
        assert len(out) == 1


class TestCheckCandidateCount:
    def test_pass(self) -> None:
        gate = _load_gate_module()
        assert gate.check_candidate_count(_good_case(), expected=50) == []

    def test_fail_duplicates_reduce_unique(self) -> None:
        gate = _load_gate_module()
        case = _good_case()
        # Inject a duplicate so unique count drops to 49
        case["candidate_genes"] = [case["causal_gene"], case["causal_gene"]] + [
            f"GENE{i:04d}" for i in range(48)
        ]
        out = gate.check_candidate_count(case, expected=50)
        assert len(out) == 1 and "49 unique" in out[0]

    def test_fail_wrong_count(self) -> None:
        gate = _load_gate_module()
        case = _good_case()
        case["candidate_genes"] = case["candidate_genes"][:30]
        out = gate.check_candidate_count(case, expected=50)
        assert len(out) == 1


class TestCheckCausalInCandidates:
    def test_pass(self) -> None:
        gate = _load_gate_module()
        assert gate.check_causal_in_candidates(_good_case()) == []

    def test_fail_causal_not_in_list(self) -> None:
        gate = _load_gate_module()
        case = _good_case(causal="BRCA1")
        # Replace candidate_genes so causal is missing
        case["candidate_genes"] = [f"GENE{i:04d}" for i in range(50)]
        out = gate.check_causal_in_candidates(case)
        assert len(out) == 1 and "not in candidate_genes" in out[0]

    def test_fail_missing_causal_field(self) -> None:
        gate = _load_gate_module()
        case = _good_case()
        case["causal_gene"] = None
        out = gate.check_causal_in_candidates(case)
        assert len(out) == 1


class TestCheckPmcCoverage:
    def test_pass(self) -> None:
        gate = _load_gate_module()
        assert gate.check_pmc_coverage(_good_case(pmc=10), min_pmc=5) == []

    def test_fail_too_few_articles(self) -> None:
        gate = _load_gate_module()
        out = gate.check_pmc_coverage(_good_case(pmc=2), min_pmc=5)
        assert len(out) == 1 and "only 2 PMC articles" in out[0]

    def test_fail_null_count(self) -> None:
        """When pmc_article_count is None (pre-B6), this check fails by design."""
        gate = _load_gate_module()
        case = _good_case()
        case["pmc_article_count"] = None
        out = gate.check_pmc_coverage(case, min_pmc=5)
        assert len(out) == 1 and "B6 must run first" in out[0]


class TestCheckCategoryBalance:
    def test_pass_balanced(self) -> None:
        gate = _load_gate_module()
        # 4 categories x 19 each = 76, well within ±20% of 19
        cases = []
        for cat in gate.CATEGORIES:
            for i in range(19):
                cases.append(_good_case(case_id=f"{cat}-{i}", category=cat))
        out = gate.check_category_balance(cases, gate.CATEGORIES, 0.20)
        assert out == []

    def test_pass_75_split_18_19_19_19(self) -> None:
        """The actual 75-case sample distribution: 18+19+19+19 — within tolerance."""
        gate = _load_gate_module()
        sizes = {"neurological": 18, "metabolic": 19, "immunological": 19, "developmental": 19}
        cases = []
        for cat, n in sizes.items():
            for i in range(n):
                cases.append(_good_case(case_id=f"{cat}-{i}", category=cat))
        # expected = 75/4 = 18.75; tolerance = 0.2*18.75 = 3.75
        # All counts {18, 19, 19, 19} are within ±3.75 of 18.75 — pass.
        out = gate.check_category_balance(cases, gate.CATEGORIES, 0.20)
        assert out == []

    def test_fail_one_category_overweight(self) -> None:
        """If one category is heavily overrepresented, balance fails."""
        gate = _load_gate_module()
        cases = []
        for i in range(80):  # neurological way overweight
            cases.append(_good_case(case_id=f"neuro-{i}", category="neurological"))
        for cat in ("metabolic", "immunological", "developmental"):
            for i in range(5):
                cases.append(_good_case(case_id=f"{cat}-{i}", category=cat))
        out = gate.check_category_balance(cases, gate.CATEGORIES, 0.20)
        assert len(out) >= 1
        assert any("neurological" in f for f in out)


class TestRunAllChecks:
    def test_all_pass(self) -> None:
        gate = _load_gate_module()
        cases = [_good_case(case_id=f"c-{i}") for i in range(76)]
        # rotate categories so balance check passes
        for i, c in enumerate(cases):
            c["category"] = gate.CATEGORIES[i % len(gate.CATEGORIES)]
        out = gate.run_all_checks(
            cases, min_hpo=3, expected_candidates=50, min_pmc=5, skip_pmc=False
        )
        assert out == []

    def test_skip_pmc_ignores_null_counts(self) -> None:
        """With skip_pmc=True, null pmc_article_count does not fail the gate."""
        gate = _load_gate_module()
        cases = [_good_case(case_id=f"c-{i}") for i in range(76)]
        for i, c in enumerate(cases):
            c["category"] = gate.CATEGORIES[i % len(gate.CATEGORIES)]
            c["pmc_article_count"] = None  # B6 not run yet
        out = gate.run_all_checks(
            cases, min_hpo=3, expected_candidates=50, min_pmc=5, skip_pmc=True
        )
        assert out == []

    def test_aggregates_failures_across_checks(self) -> None:
        """Multiple distinct failures are all reported in the same run."""
        gate = _load_gate_module()
        cases = [_good_case(case_id=f"c-{i}") for i in range(20)]
        cases[0]["hpo_terms"] = []
        cases[1]["pmc_article_count"] = 1
        # Don't fix categories → balance check will also fail
        out = gate.run_all_checks(
            cases, min_hpo=3, expected_candidates=50, min_pmc=5, skip_pmc=False
        )
        # At least: 1 hpo failure + 1 pmc failure + at least 1 category-balance failure
        assert len(out) >= 3
        assert any("HPO terms" in f for f in out)
        assert any("PMC articles" in f for f in out)
