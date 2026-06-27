# Figshare upload checklist — P1 (methods / shared foundation)

One Figshare item, tag `paper-methods-v1.0`. Author: **Johanna Angulo**. License: AGPL-3.0 (code) / CC BY 4.0 (cohort).

> This methods item is **code only** (type: Software). The n=1,047 cohort is a
> **separate Dataset item** — see `release/cohort/FIGSHARE_CHECKLIST.md` — and is
> referenced here by its DOI, not duplicated.

## Upload these files

| # | File (in `figshare_uploads/`) | What | License |
|---|---|---|---|
| 1 | `paper-methods-v1.0_code_<commit>.zip` | corpus/cohort pipeline code, tests, env/build config, methods docs, `REPRODUCE.md`, `MANIFEST.tsv` | AGPL-3.0 |
| 2 | `paper-methods-v1.0_code_<commit>.zip.sha256` + `CHECKSUMS_paper-methods.sha256` | integrity | — |
| 3 | `release/paper-methods/README_FIGSHARE.md` | item description (paste as the Figshare description) | — |

After the cohort item is published, paste its **DOI** into this item's
`README_FIGSHARE.md` (`Benchmark cohort DOI:` line).

## Reference, do NOT upload (cite by pinned version)

- PMC-OA Qdrant index (323 GB) + chunk/parsed JSONL — **recipe-only** (rebuild via code; verify fingerprint `52,777,395`).
- HPO / MONDO / GO / HGNC ontologies; Phenopacket Store v0.1.26; PubMedBERT — upstream URLs in `MANIFEST.tsv` / README.
- ACMG-evidence SFT set — packaged in the `geno_agent_variant` repo; cross-reference its DOI.

## After upload — REQUIRED

- [ ] Record the **P1 Figshare DOI**.
- [ ] Paste it into `release/paper-methods/README_FIGSHARE.md` (`Shared-foundation DOI:` line) and into P2's `README_FIGSHARE.md`.
- [ ] Carry the same DOI into the separate **`geno_agent_variant` (P3)** session so P3 references — not duplicates — this foundation.
