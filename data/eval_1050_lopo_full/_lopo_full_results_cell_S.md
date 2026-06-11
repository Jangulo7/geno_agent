# LOPO full-cohort results — Cell S

Cases with both arms present: **1047**

## 1. Control vs LOPO (paired, geno_agent against itself)

| Cohort | n | control top-1 | LOPO top-1 | Δ | discordant (ctrl-only/lopo-only) | McNemar p | ctrl top-5/10 | lopo top-5/10 |
|---|--:|--:|--:|--:|:--:|--:|--:|--:|
| full | 1047 | 0.726 | 0.711 | +0.015 | 16/0 | 3e-05 | 0.798/0.819 | 0.779/0.800 |
| overlap_present | 765 | 0.677 | 0.656 | +0.021 | 16/0 | 3e-05 | 0.750/0.774 | 0.724/0.749 |
| overlap_absent (FAIR) | 282 | 0.858 | 0.858 | +0.000 | 0/0 | 1.0 | 0.929/0.940 | 0.929/0.940 |

## 2. Does geno_agent's advantage survive source-paper removal? (LOPO vs curated tools)

| Cohort | n | LOPO top-1 | Exomiser K top-1 | Δ(S-K) | p(S-K) | LIRICAL M top-1 | Δ(S-M) | p(S-M) |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| full | 1047 | 0.711 | 0.691 | +0.020 | 0.1823 | 0.924 | -0.213 | 0.0 |
| overlap_absent (FAIR) | 282 | 0.858 | 0.780 | +0.078 | 0.01544 | 0.777 | +0.082 | 0.014 |

## 3. Source-paper-in-retrieval leak, by annotation-overlap status

| Cohort | n | source-in-causal-pool rate |
|---|--:|--:|
| full | 1047 | 0.117 |
| overlap_present | 765 | 0.108 |
| overlap_absent (FAIR) | 282 | 0.142 |

## 4. Per-MONDO control vs LOPO top-1

| MONDO | n | control | LOPO | Δ |
|---|--:|--:|--:|--:|
| developmental | 250 | 0.720 | 0.704 | +0.016 |
| immunological | 300 | 0.747 | 0.743 | +0.003 |
| metabolic | 250 | 0.872 | 0.864 | +0.008 |
| neurological | 247 | 0.559 | 0.522 | +0.036 |
