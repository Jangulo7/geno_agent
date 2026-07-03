"""Tests for src.baselines.llm_only — the Cell O LLM-only (no-retrieval) baseline.

The LLM call is mocked, so these run in CI without a vLLM server. The model
returns a JSON array of gene symbols (a ranked list); confidence is derived from
rank position and parsing is tolerant of truncation. Covers:
  * happy path: valid ranking -> correct schema, ranks, is_causal, order
  * partial ranking: omitted genes appended in input order after ranked ones
  * truncation recovery: a cut-off array still yields its ranked prefix
  * fallbacks: connection error / no recoverable gene -> input order, no crash
  * the fallback carries no positional signal (preserves seed-shuffled order)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from src.baselines import llm_only
from src.baselines.llm_only import _parse_ranking, rank_llm_only

CASE = {
    "case_id": "GENE3:PMID_1",
    "candidate_genes": ["GENE1", "GENE2", "GENE3", "GENE4"],
    "causal_gene": "GENE3",
}


def _resp(text: str) -> SimpleNamespace:
    """Minimal stand-in for LlmResponse (only ``.text`` is read)."""
    return SimpleNamespace(text=text)


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


def test_happy_path_preserves_model_order():
    with mock.patch.object(
        llm_only, "generate", return_value=_resp('["GENE3", "GENE1", "GENE2", "GENE4"]')
    ):
        payload = rank_llm_only(CASE, hpo_labels=["Seizure"])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    assert [p["symbol"] for p in payload] == ["GENE3", "GENE1", "GENE2", "GENE4"]
    assert payload[0]["symbol"] == "GENE3" and payload[0]["final_rank"] == 1
    confs = [p["aggregate_confidence"] for p in payload]
    assert confs == sorted(confs, reverse=True)  # non-increasing with rank


def test_partial_ranking_appends_missing_in_input_order():
    with mock.patch.object(llm_only, "generate", return_value=_resp('["GENE2", "GENE4"]')):
        payload = rank_llm_only(CASE, hpo_labels=[])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    order = [p["symbol"] for p in payload]
    assert order[:2] == ["GENE2", "GENE4"]  # ranked genes first, in model order
    assert order[2:] == ["GENE1", "GENE3"]  # omitted kept in input order
    conf = {p["symbol"]: p["aggregate_confidence"] for p in payload}
    assert conf["GENE1"] == 0.0 and conf["GENE3"] == 0.0  # omitted carry no signal
    assert conf["GENE2"] > 0.0 and conf["GENE4"] > 0.0


def test_truncated_array_recovers_ranked_prefix():
    # Verbose reply cut off mid-array: not valid JSON, but the prefix is recoverable.
    with mock.patch.object(llm_only, "generate", return_value=_resp('["GENE4", "GENE2", "GEN')):
        payload = rank_llm_only(CASE, hpo_labels=[])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    order = [p["symbol"] for p in payload]
    assert order[:2] == ["GENE4", "GENE2"]  # ranked prefix salvaged, in order
    assert order[2:] == ["GENE1", "GENE3"]  # rest in input order


def test_connection_error_falls_back():
    with mock.patch.object(llm_only, "generate", side_effect=RuntimeError("no server")):
        payload = rank_llm_only(CASE, hpo_labels=["Seizure"])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    assert [p["symbol"] for p in payload] == CASE["candidate_genes"]
    assert all(p["aggregate_confidence"] == 0.0 for p in payload)


def test_no_recoverable_gene_falls_back():
    with mock.patch.object(
        llm_only, "generate", return_value=_resp("I cannot determine a ranking.")
    ):
        payload = rank_llm_only(CASE, hpo_labels=["Seizure"])
    _assert_valid_payload(payload, CASE["candidate_genes"], "GENE3")
    assert [p["symbol"] for p in payload] == CASE["candidate_genes"]


def test_parse_ranking_json_dedupes_and_drops_unknown():
    out = _parse_ranking(
        '["GENE1", "GENE1", "NOTACANDIDATE", "GENE2"]', {"GENE1", "GENE2", "GENE3"}
    )
    assert out == ["GENE1", "GENE2"]  # first occurrence wins, order preserved


def test_parse_ranking_regex_recovers_from_non_json():
    # No brackets/quotes at all -> regex path picks candidate symbols in order.
    out = _parse_ranking("GENE2 then GENE1 then nonsense", {"GENE1", "GENE2"})
    assert out == ["GENE2", "GENE1"]


def test_parse_ranking_none_when_no_candidate_present():
    assert _parse_ranking("no genes here", {"GENE1"}) is None
    assert _parse_ranking("[]", {"GENE1"}) is None
