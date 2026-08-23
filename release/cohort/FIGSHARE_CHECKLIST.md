# Figshare upload checklist — Benchmark Cohort (Dataset item)

Figshare item type: **Dataset**. License: **CC BY 4.0**. Author: **Johanna Angulo**.
Lives in the "GenoAgent" project alongside the methods and system items.

## Upload these files

| # | File (in `figshare_uploads/`) | What | License |
|---|---|---|---|
| 1 | `genoagent-cohort-n1047-v1.0.zip` | full n=1,047 cohort (`test_cases.jsonl` + sidecars + 01–06 provenance stages) + `MANIFEST.tsv` + data descriptor + per-file `CHECKSUMS.sha256` | CC BY 4.0 |
| 2 | `release/cohort/README_FIGSHARE.md` | item description (paste into the Figshare description field — see `figshare_uploads/FIGSHARE_WEB_TEXT.md`) | — |

> Do **not** upload the `.sha256` sidecar. The live records carry the zip and the
> Croissant descriptor only; integrity is covered by `CHECKSUMS.sha256` inside the
> bundle and by the digests in `figshare_uploads/UPLOAD_MAP.md`.

## Metadata to set (drives discoverability → citations)

- **Type:** Dataset · **License:** CC BY 4.0 · **Version:** v1.0
- **Keywords:** rare disease, gene prioritisation, benchmark, Human Phenotype Ontology,
  Phenopacket, clinical genomics, retrieval-augmented generation
- **Related identifiers:** link to the methods/foundation item DOI (IsDerivedFrom /
  IsSupplementedBy) and to GA4GH Phenopacket Store v0.1.26.

## After upload — REQUIRED

- [ ] Record the **cohort DOI**.
- [ ] Paste it into the methods item's `README_FIGSHARE.md` (`Benchmark cohort DOI:` line)
      and into the GenoAgent (P2) item description.
- [ ] Cite the cohort DOI in the manuscript's Data Availability statement.
