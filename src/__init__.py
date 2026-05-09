"""geno_agent — Phase 2 application code (master plan §11).

This package houses the agent-layer code that consumes the Phase 1A retrieval
substrate and the Phase 1B test cases. Sub-packages:

  * ``agents``  — LangGraph state graph + four agent nodes (master plan §11.1)
  * ``api``     — FastAPI + copilotkit-sdk-python wrapper (master plan §11.2)
  * ``tools``   — shared helpers (HPO expansion, HGNC validation, Qdrant search)
"""
