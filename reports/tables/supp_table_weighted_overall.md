# Supplementary table — stratum-weighted overall top-1

Unweighted = mean over all 1,047 cases (immunological oversampled to 300). Equal-weighted = each MONDO supercategory weighted 25 % (removes the oversampling distortion).

| Cell | unweighted top-1 | equal-weighted top-1 | developmental | immunological | metabolic | neurological |
|---|--:|--:|--:|--:|--:|--:|
| K (Exomiser) | 0.6905 | 0.6906 | 0.764 | 0.680 | 0.788 | 0.530 |
| M (LIRICAL) | 0.9236 | 0.9229 | 0.952 | 0.937 | 0.908 | 0.895 |
| L (rerank) | 0.6982 | 0.6970 | 0.688 | 0.713 | 0.844 | 0.543 |
| S (geno_agent) | 0.7259 | 0.7243 | 0.720 | 0.747 | 0.872 | 0.559 |

**geno_agent (S) - Exomiser (K):** unweighted Δ = +0.0353; equal-weighted Δ = +0.0338. Direction and magnitude of the geno_agent advantage are invariant to stratum weighting.
