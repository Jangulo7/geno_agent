# Figshare upload checklist — Benchmark Cohort (Dataset item)

Figshare item type: **Dataset**. License: **CC BY 4.0**. Author: **Johanna Angulo**.
Lives in the "GenoAgent" project alongside the methods and system items.

## Upload these files

| # | File (in `figshare_uploads/`) | What | License |
|---|---|---|---|
| 1 | `genoagent-cohort-n1047-v1.0.zip` | full n=1,047 cohort (`test_cases.jsonl` + sidecars + 01–06 provenance stages) + `MANIFEST.tsv` + data descriptor + per-file `CHECKSUMS.sha256` | CC BY 4.0 |
| 2 | `genoagent-cohort-n1047-v1.0.zip.sha256` | integrity (zip-level) | — |
| 3 | `release/cohort/README_FIGSHARE.md` | item description / data descriptor (paste as the Figshare description) | — |

## Metadata to set (drives discoverability → citations)

- **Type:** Dataset · **License:** CC BY 4.0 · **Version:** v1.0
- **Keywords:** rare disease, gene prioritization, benchmark, Human Phenotype Ontology,
  Phenopacket, clinical genomics, retrieval-augmented generation
- **Related identifiers:** link to the methods/foundation item DOI (IsDerivedFrom /
  IsSupplementedBy) and to GA4GH Phenopacket Store v0.1.26.

## After upload — REQUIRED

- [ ] Record the **cohort DOI**.
- [ ] Paste it into the methods item's `README_FIGSHARE.md` (`Benchmark cohort DOI:` line)
      and into the GenoAgent (P2) item description.
- [ ] Cite the cohort DOI in the manuscript's Data Availability statement.
