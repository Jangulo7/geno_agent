# LEA ablation — cross-LLM comparison (n = 300)

Cohort: n = 300 stratified (subset of the full n = 1,047 evaluation). overlap_absent = 84, overlap_present = 216.

Production = Qwen3-8B run on the same cases (extracted from data/eval_1050/cell_S_responses/). Ablation models replayed the saved LEA prompts via OpenRouter — same retrieval, same rerank, same chunks; only the LLM backend differs.

## __all__ (n = 300)

| Model | top-1 | top-5 | top-10 | MRR | NDCG@10 |
|---|---|---|---|---|---|
| qwen3-8b (production) | 0.717 [0.663, 0.763] | 0.783 [0.737, 0.827] | 0.807 [0.763, 0.850] | 0.749 [0.703, 0.793] | 0.761 [0.718, 0.807] |
| anthropic_claude-sonnet-4.6 | 0.767 [0.720, 0.810] | 0.810 [0.763, 0.853] | 0.820 [0.777, 0.863] | 0.788 [0.746, 0.830] | 0.795 [0.751, 0.838] |
| deepseek_deepseek-chat-v3-0324 | 0.737 [0.683, 0.783] | 0.790 [0.743, 0.833] | 0.800 [0.757, 0.843] | 0.759 [0.715, 0.803] | 0.769 [0.723, 0.816] |
| qwen_qwen3-32b | 0.563 [0.507, 0.620] | 0.583 [0.520, 0.640] | 0.590 [0.533, 0.647] | 0.573 [0.522, 0.625] | 0.576 [0.521, 0.632] |

### Paired Δ vs Qwen3-8B production

| Model | Δ top-1 | 95 % CI | A>B | B>A | McNemar p | sig |
|---|---:|---|---:|---:|---:|:-:|
| anthropic_claude-sonnet-4.6 | +0.0500 | [+0.0267, +0.0733] | 15 | 0 | 0.00006 | ★ |
| deepseek_deepseek-chat-v3-0324 | +0.0200 | [+0.0033, +0.0400] | 7 | 1 | 0.07031 | ★ |
| qwen_qwen3-32b | -0.1533 | [-0.2033, -0.1067] | 6 | 52 | 0.00000 | ★ |

## overlap_absent (n = 84)

| Model | top-1 | top-5 | top-10 | MRR | NDCG@10 |
|---|---|---|---|---|---|
| qwen3-8b (production) | 0.869 [0.798, 0.941] | 0.917 [0.845, 0.964] | 0.941 [0.881, 0.988] | 0.894 [0.833, 0.948] | 0.905 [0.844, 0.956] |
| anthropic_claude-sonnet-4.6 | 0.893 [0.821, 0.952] | 0.941 [0.881, 0.988] | 0.941 [0.881, 0.988] | 0.911 [0.854, 0.965] | 0.918 [0.862, 0.966] |
| deepseek_deepseek-chat-v3-0324 | 0.881 [0.798, 0.952] | 0.917 [0.857, 0.976] | 0.929 [0.869, 0.976] | 0.897 [0.833, 0.954] | 0.905 [0.845, 0.956] |
| qwen_qwen3-32b | 0.679 [0.571, 0.774] | 0.691 [0.595, 0.786] | 0.702 [0.595, 0.798] | 0.686 [0.579, 0.788] | 0.690 [0.596, 0.786] |

### Paired Δ vs Qwen3-8B production

| Model | Δ top-1 | 95 % CI | A>B | B>A | McNemar p | sig |
|---|---:|---|---:|---:|---:|:-:|
| anthropic_claude-sonnet-4.6 | +0.0238 | [+0.0000, +0.0595] | 2 | 0 | 0.50000 |  |
| deepseek_deepseek-chat-v3-0324 | +0.0119 | [-0.0238, +0.0476] | 2 | 1 | 1.00000 |  |
| qwen_qwen3-32b | -0.1905 | [-0.2976, -0.0952] | 2 | 18 | 0.00040 | ★ |

## overlap_present (n = 216)

| Model | top-1 | top-5 | top-10 | MRR | NDCG@10 |
|---|---|---|---|---|---|
| qwen3-8b (production) | 0.657 [0.602, 0.722] | 0.732 [0.671, 0.787] | 0.755 [0.699, 0.806] | 0.692 [0.631, 0.747] | 0.706 [0.649, 0.760] |
| anthropic_claude-sonnet-4.6 | 0.718 [0.662, 0.778] | 0.759 [0.699, 0.815] | 0.773 [0.718, 0.824] | 0.740 [0.681, 0.794] | 0.747 [0.690, 0.800] |
| deepseek_deepseek-chat-v3-0324 | 0.681 [0.625, 0.741] | 0.741 [0.681, 0.801] | 0.750 [0.694, 0.801] | 0.706 [0.643, 0.760] | 0.716 [0.656, 0.769] |
| qwen_qwen3-32b | 0.518 [0.458, 0.588] | 0.542 [0.477, 0.611] | 0.546 [0.481, 0.611] | 0.529 [0.463, 0.595] | 0.532 [0.467, 0.597] |

### Paired Δ vs Qwen3-8B production

| Model | Δ top-1 | 95 % CI | A>B | B>A | McNemar p | sig |
|---|---:|---|---:|---:|---:|:-:|
| anthropic_claude-sonnet-4.6 | +0.0602 | [+0.0278, +0.0926] | 13 | 0 | 0.00024 | ★ |
| deepseek_deepseek-chat-v3-0324 | +0.0231 | [+0.0046, +0.0463] | 5 | 0 | 0.06250 | ★ |
| qwen_qwen3-32b | -0.1389 | [-0.1898, -0.0880] | 4 | 34 | 0.00000 | ★ |

## Per-MONDO breakdown — top-1 (point estimate only)

| Model | developmental n=75 | immunological n=75 | metabolic n=75 | neurological n=75 |
|---|---|---|---|---|
| qwen3-8b (production) | 0.693 | 0.800 | 0.840 | 0.533 |
| anthropic_claude-sonnet-4.6 | 0.747 | 0.813 | 0.893 | 0.613 |
| deepseek_deepseek-chat-v3-0324 | 0.720 | 0.813 | 0.853 | 0.560 |
| qwen_qwen3-32b | 0.573 | 0.613 | 0.667 | 0.400 |

## Cost + latency per ablation model (n cohort)

| Model | Total $ | Mean latency (s) | API/parse errors |
|---|---:|---:|---:|
| anthropic_claude-sonnet-4.6 | 19.9465 | 13.87 | 22 |
| deepseek_deepseek-chat-v3-0324 | 1.0471 | 25.09 | 1 |
| qwen_qwen3-32b | 0.4164 | 8.71 | 66 |
