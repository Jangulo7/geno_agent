# Supplementary table — multiplicity correction

Pre-declared primary endpoint: top-1 accuracy of geno_agent (Cell S) vs each curated baseline on the deconfounded fair cohort. Holm controls family-wise error; Benjamini-Hochberg controls FDR.

### Primary family — fair-cohort top-1 (2 tests)

| Comparison | raw p | Holm p | BH p | survives alpha=0.05 (Holm) |
|---|--:|--:|--:|:--:|
| geno_agent (S) vs Exomiser (K), top-1, FAIR cohort | 0.01544 | 0.02800 | 0.01544 | yes |
| geno_agent (S) vs LIRICAL (M), top-1, FAIR cohort | 0.01400 | 0.02800 | 0.01544 | yes |

### Supportive family — full-cohort + recency top-1 (2 tests)

| Comparison | raw p | Holm p | BH p | survives alpha=0.05 (Holm) |
|---|--:|--:|--:|:--:|
| geno_agent (S) vs Exomiser (K), top-1, full cohort | 0.01866 | 0.01866 | 0.01866 | yes |
| geno_agent (S) vs Exomiser (K), top-1, post-2020 | 0.00007 | 0.00014 | 0.00014 | yes |

**Verdict:** All primary comparisons remain significant after Holm correction.
