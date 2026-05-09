"""Deterministic seeding helper for every stochastic surface in the pipeline.

This module is imported at the top of every script that performs any embedding,
sampling, chunking, or other randomized work. Centralizing the seed application
here means a single change point if the pinned seed in `.env` changes, and it
guarantees that no entrypoint forgets to seed `torch`, `numpy`, or Python's
built-in `random` independently.

The reference implementation lives in master plan §2.2; this is the working
copy. Reproducibility per master plan §4.1.3 depends on every entrypoint
calling :func:`apply_seeds` before any work is done.

Typical use::

    from scripts.utils.seed import apply_seeds

    apply_seeds()  # picks up RANDOM_SEED from env, defaults to 42
"""

from __future__ import annotations

import hashlib
import os
import random

import numpy as np


def apply_seeds(seed: int = 42) -> None:
    """Apply deterministic seeds across every stochastic surface used in the pipeline.

    Sets ``PYTHONHASHSEED`` (only if unset — once Python is running, mutating it
    has no effect, but exporting it for child processes is still useful), seeds
    the ``random`` and ``numpy`` RNGs, and best-effort seeds PyTorch CPU and
    CUDA RNGs plus cuDNN determinism flags. ``torch.use_deterministic_algorithms``
    is called with ``warn_only=True`` so that cuBLAS kernels with no
    deterministic implementation log a warning rather than crash the embedding
    job — see master plan §2.2 for the rationale.

    Args:
        seed: Integer seed value. Defaults to 42 to match ``.env``'s
            ``RANDOM_SEED`` and the project's pinned reproducibility contract.

    Returns:
        None. Side effects only: modifies environment, RNG state, and (if torch
        is installed) cuDNN backend flags.
    """
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        torch.use_deterministic_algorithms(True, warn_only=True)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except ImportError:
        pass


def stable_hash(s: str) -> int:
    """Cross-process-stable hash of a string.

    Replaces Python's built-in :func:`hash`, which is salted per-process via
    ``PYTHONHASHSEED`` and therefore unsafe for any artifact that must remain
    byte-identical across runs (e.g., chunk IDs, Qdrant point IDs).

    Args:
        s: Input string.

    Returns:
        A non-negative 64-bit integer derived from a BLAKE2b digest of the
        UTF-8 encoding of ``s``. Stable across processes, machines, and
        Python versions.
    """
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")
