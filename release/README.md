# Release bundles — Figshare packaging for P1 and P2

This directory defines, **per paper**, the exact code and data/resource artifacts
that make up a citable, reproducible release. Nothing here moves or rewrites the
working repository — the bundles are assembled *from* a git tag plus on-disk data.

## The three papers (and where they live)

| Paper | Scope | Repository | Tag |
|---|---|---|---|
| **P1** | Methods / shared foundation (PMC-OA corpus + Qdrant index build, ontology pinning, n=1,047 cohort construction) | this repo (`geno_agent`) | `paper-methods-v1.4` |
| **P2** | GenoAgent — four-agent LangGraph RAG gene prioritisation + evaluation | this repo (`geno_agent`) | `paper-genoagent-v1.8` |
| **P3** | Safety benchmark (variant interpretation) — **reuses P1's shared foundation by DOI, and forks P2's agent code under AGPL** | separate repo `geno_agent_variant` | (in that repo) |

The **shared foundation** (Qdrant PMC-OA index recipe, pinned ontologies,
Phenopacket cohort, `data/MANIFEST.tsv`) is owned by **P1** and packaged **once**.
P2 and the external P3 repo **reference it by DOI**, never duplicate it.

## Layout

```
release/
├── README.md                      # this file
├── build_figshare_bundles.sh      # builds code zips (git archive) + checksums into ../figshare_uploads/
├── cohort/                        # Benchmark cohort — standalone Dataset item (own DOI)
│   ├── README_FIGSHARE.md         # data descriptor (provenance, data dictionary, license, citation, regeneration)
│   └── FIGSHARE_CHECKLIST.md
├── paper-methods/                 # P1 methods/foundation — Software item (code only; references the cohort DOI)
│   ├── README_FIGSHARE.md         # Figshare item description (title, abstract, license, citation, tag+commit)
│   ├── REPRODUCE.md               # exact commands to rebuild the corpus/index/cohort
│   ├── code_paths.txt             # pathspecs fed to `git archive` for the P1 code zip
│   ├── artifacts_manifest.tsv     # every data/resource artifact -> action (upload/reference/recipe/exclude)
│   └── FIGSHARE_CHECKLIST.md
└── paper-genoagent/               # P2 system — Software + data item
    ├── README_FIGSHARE.md
    ├── REPRODUCE.md
    ├── code_paths.txt
    ├── artifacts_manifest.tsv
    └── FIGSHARE_CHECKLIST.md
```

## Figshare items (in the "GenoAgent" project)

| Item | Type | Bundle(s) | DOI cited by |
|---|---|---|---|
| **Benchmark cohort (n=1,047)** | Dataset (CC BY 4.0) | `genoagent-cohort-n1047-v1.0.zip` | methods item, P2, manuscripts |
| **Methods / foundation** | Software (AGPL) | `paper-methods-v1.4_code_*.zip` | P2, external P3 repo |
| **GenoAgent system** | Software (AGPL) | `paper-genoagent-v1.8_code_*.zip` + `_data.zip` | manuscript |

## How to build (after the tags exist)

```bash
# 1. create the annotated tags (done once, after review/merge — see RELEASE checklist)
# 2. build the code zips + sha256 from those tags:
bash release/build_figshare_bundles.sh paper-methods-v1.4
bash release/build_figshare_bundles.sh paper-genoagent-v1.8
# 3. assemble the data bundles (cohort Dataset + P2 results/manuscript):
bash release/assemble_data_bundles.sh
# outputs land in ../figshare_uploads/ (gitignored)
```

Data/resource artifacts that are **not** code (cohort JSONL, eval result JSONs,
figures) are listed in each paper's `artifacts_manifest.tsv` with an explicit
action and are assembled separately — many live on disk and are gitignored, so
they cannot come from `git archive`.

## Hard rules for these bundles

- **Author is Johanna Angulo only.** No AI tool is credited anywhere.
- **License: AGPL-3.0** (code). Data artifacts keep their upstream licenses.
- **Never upload:** the 323 GB Qdrant index / PMC chunk text (mixed CC, recipe-only),
  `reports/cover_letter_genome_medicine.md` (personal PII), `.env`, model weights.
- **Reference, don't host:** ontologies, phenopackets, models, baseline tools
  (Exomiser/LIRICAL) — pin version + cite upstream.
