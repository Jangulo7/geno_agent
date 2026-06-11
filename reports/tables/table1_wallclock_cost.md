| Cell | System | n | Wallclock (h) | Mean s/case | Hardware | Cost (USD) | Local |
|---|---|---|---|---|---|---|---|
| D | Multi-agent baseline | 1,047 | 4.8 | 16.5 | 1 GPU + Qdrant | $0.00 | ✓ |
| K | Exomiser HPO-only | 1,047 | 0.8 | 2.7 | CPU only | $0.00 | ✓ |
| L | + CE-rerank (inside) | 1,047 | 6.2 | 21.3 | 1 GPU + Qdrant | $0.00 | ✓ |
| M | LIRICAL HPO-only | 1,047 | 1.4 | 4.8 | CPU only | $0.00 | ✓ |
| S | geno_agent (Cell S) | 1,047 | 7.6 | 26.1 | 1 GPU + Qdrant + vLLM | $0.00 | ✓ |
| N | RRF ensemble (M+S) | 1,047 | <0.1 | <0.1 | post-hoc | $0.00 | ✓ |
| — | RAGAS (GPT-4o judge) | 600 | — | — | OpenAI API | $95.00 | ✗ |
| — | DeepEval (GPT-4o judge) | 100 | — | — | OpenAI API | $1.40 | ✗ |
| — | LLM-family ablation | 300x3 | — | — | OpenRouter API | $21.42 | ✗ |
