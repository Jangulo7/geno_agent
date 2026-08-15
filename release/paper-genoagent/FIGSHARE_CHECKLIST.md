# Figshare upload checklist — P2 (GenoAgent)

One Figshare item, tag `paper-genoagent-v1.3`. Author: **Johanna Angulo**. License: AGPL-3.0. Depends on P1's foundation by DOI.

## Upload these files

| # | File (in `figshare_uploads/`) | What | License |
|---|---|---|---|
| 1 | `paper-genoagent-v1.3_code_<commit>.zip` | agents, tools, baselines, eval harness, demos, tests, docs, `REPRODUCE.md` | AGPL-3.0 |
| 2 | `paper-genoagent-v1.3_data.zip` | committed `eval_1050/` + `eval_hard/` results (incl. Cell R) + `lopo_full/` summaries + figures + tables + **text-stripped rationale derivative** | AGPL-3.0 |
| 3 | `*.sha256` for items 1–2 + `CHECKSUMS_paper-genoagent.sha256` | integrity | — |
| 4 | `release/paper-genoagent/README_FIGSHARE.md` | item description (paste as the Figshare description) | — |

## Reference, do NOT upload

- **Shared foundation** (Qdrant index, ontologies, n=1,047 cohort, `MANIFEST.tsv`) → cite **P1's DOI**.
- Qwen3-8B, vLLM, MedCPT, Exomiser 14.0.2, LIRICAL 2.4.0 → upstream by pinned version.

## Explicitly excluded (do NOT upload)

- `data/eval_1050/cell_S_responses/` + `cell_L_responses/` (1.9 GB) — embed **verbatim PMC-OA text** (mixed CC); not license-clean. The published `cell_S_rationale_derivative/` (verbatim text stripped) replaces them.
- `reports/cover_letter_genome_medicine.md` — personal PII.

## After upload

- [ ] Paste P1's **Shared-foundation DOI** into this item's `README_FIGSHARE.md` (`Shared-foundation DOI (from P1):` line).
- [ ] Record the **P2 Figshare DOI** for the manuscript's Data Availability statement.
