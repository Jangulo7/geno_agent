"""Tests for src.baselines.llm_only — the Cell O LLM-only (no-retrieval) baseline.

The LLM call is mocked, so these run in CI without a vLLM server. Covers:
  * happy path: valid ranking -> correct schema, ranks, is_causal, order
  * partial scoring: unscored genes fall to input order after scored ones
  * fallbacks: invalid JSON / connection error / non-list -> input order, no crash
  * the fallback carries no positional signal (preserves seed-shuffled order)
"""

from __future__ import annotations

import json
from unittest import mock

from src.baselines import llm_only
from src.baselines.llm_only import _parse_response, rank_llm_only

CASE = {
    "case_id": "GENE3:PMID_1",
    "candidate_genes": ["GENE1", "GENE2", "GENE3", "GENE4"],
    "causal_gene": "GENE3",
}


def _assert_valid_payload(payload: list[dict], candidates: list[str], causal: str) -> None:
    """Schema + invariants shared by every path."""
    assert [p["symbol"] for p in payload].__len__() == len(candidates)
    assert {p["symbol"] for p in payload} == set(candidates)  # all genes, no dupes
    assert [p["final_rank"] for p in payload] == list(range(1, len(candidates) + 1))
    causal_entries = [p for p in payload if p["is_causal"]]
    assert len(causal_entries) == 1 and causal_entries[0]["symbol"] == causal
    for p in payload:
        assert p["supporting_chunks"] == []
        assert 0.0 <= p["aggregate_confidence"] <= 1.0


def test_happy_path_orders_by_confidence():
    ranking = [
        {"gene": "GENE3", "confidence": 0.9, "rationale": "best"},
        {"gene": "GENE1", "confidence": 0.4, "rationale": "meh"},
        {"gene": "GENE2", "confidence": 0.1, "rationale": "no"},
        {"gene": "GENE4", "confidence": 0.05, "rationale": "no"},
    ]
    with mock.patch.object(llm_only, "generate_json", return_value=(ranking, None)):
        payload = rank_llm_only(CASE, hpo_labels=["Seizure"])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    assert payload[0]["symbol"] == "GENE3"  # highest confidence ranked first
    assert payload[0]["final_rank"] == 1


def test_partial_scoring_falls_to_input_order():
    # LLM only scores 2 of 4 genes; the rest keep input order after the scored ones.
    ranking = [
        {"gene": "GENE2", "confidence": 0.8, "rationale": "x"},
        {"gene": "GENE4", "confidence": 0.6, "rationale": "y"},
    ]
    with mock.patch.object(llm_only, "generate_json", return_value=(ranking, None)):
        payload = rank_llm_only(CASE, hpo_labels=[])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    order = [p["symbol"] for p in payload]
    assert order[:2] == ["GENE2", "GENE4"]  # scored genes first, by confidence
    assert order[2:] == ["GENE1", "GENE3"]  # unscored kept in input order


def test_invalid_json_falls_back_to_input_order():
    with mock.patch.object(
        llm_only, "generate_json", side_effect=json.JSONDecodeError("bad", "doc", 0)
    ):
        payload = rank_llm_only(CASE, hpo_labels=["Seizure"])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    assert [p["symbol"] for p in payload] == CASE["candidate_genes"]  # exact input order
    assert all(p["aggregate_confidence"] == 0.0 for p in payload)


def test_connection_error_falls_back():
    with mock.patch.object(llm_only, "generate_json", side_effect=RuntimeError("no server")):
        payload = rank_llm_only(CASE, hpo_labels=["Seizure"])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    assert [p["symbol"] for p in payload] == CASE["candidate_genes"]


def test_non_list_response_falls_back():
    with mock.patch.object(llm_only, "generate_json", return_value=({"oops": 1}, None)):
        payload = rank_llm_only(CASE, hpo_labels=["Seizure"])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    assert [p["symbol"] for p in payload] == CASE["candidate_genes"]


def test_parse_response_ignores_unknown_and_duplicate_genes():
    parsed = [
        {"gene": "GENE1", "confidence": 0.5},
        {"gene": "GENE1", "confidence": 0.9},  # duplicate -> first wins
        {"gene": "NOTACANDIDATE", "confidence": 0.99},  # unknown -> ignored
        {"gene": "GENE2", "confidence": 2.0},  # out of range -> clamped to 1.0
    ]
    out = _parse_response(parsed, {"GENE1", "GENE2", "GENE3", "GENE4"})
    assert out == {"GENE1": 0.5, "GENE2": 1.0}


def test_parse_response_none_on_malformed():
    assert _parse_response("not a list", {"GENE1"}) is None
    assert _parse_response([], {"GENE1"}) is None
