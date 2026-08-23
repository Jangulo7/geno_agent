# Figshare upload checklist — P1 (methods / shared foundation)

One Figshare item, tag `paper-methods-v1.4`. Author: **Johanna Angulo**. License: AGPL-3.0 (code) / CC BY 4.0 (cohort).

> Run `bash release/verify_p1_deposit.sh paper-methods-v1.4` before uploading. It
> asserts that every file the manuscript cites is in the bundle, that no
> manuscript source has leaked in, and that the tag carries the corrected RRF
> label. Tags v1.0–v1.3 fail that last check and must not be archived.

> This methods item is **code only** (type: Software). The n=1,047 cohort is a
> **separate Dataset item** — see `release/cohort/FIGSHARE_CHECKLIST.md` — and is
> referenced here by its DOI, not duplicated.

## Upload these files

| # | File (in `figshare_uploads/`) | What | License |
|---|---|---|---|
| 1 | `paper-methods-v1.4_code_<commit>.zip` | corpus/cohort pipeline code, tests, env/build config, methods docs, `REPRODUCE.md`, `MANIFEST.tsv`, the figure renderer, `release/index_fingerprint/`, `retained_pmcids.txt` | AGPL-3.0 |
> Do **not** upload the `.sha256` sidecars. The published cohort records carry
> their zip plus a Croissant descriptor only; keep this record consistent. Integrity
> is covered inside the bundle and by the digests in
> `figshare_uploads/UPLOAD_MAP.md`.
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
