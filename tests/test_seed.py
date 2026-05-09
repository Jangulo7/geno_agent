"""Tests for the deterministic seeding utility (scripts/utils/seed.py).

Verifies the reproducibility contract documented in master plan §4.1.3 and
the seed util's docstring: identical inputs must produce identical outputs
across runs and Python invocations.
"""

from __future__ import annotations

import hashlib
import os
import random

import numpy as np

from scripts.utils.seed import apply_seeds, stable_hash


class TestApplySeeds:
    """``apply_seeds`` should yield reproducible RNG state across runs."""

    def test_random_seed_reproducible(self) -> None:
        """Two calls with the same seed produce identical ``random`` draws."""
        apply_seeds(42)
        first = [random.random() for _ in range(10)]
        apply_seeds(42)
        second = [random.random() for _ in range(10)]
        assert first == second

    def test_numpy_seed_reproducible(self) -> None:
        """Two calls with the same seed produce identical numpy draws."""
        apply_seeds(42)
        first = np.random.rand(10)
        apply_seeds(42)
        second = np.random.rand(10)
        assert np.array_equal(first, second)

    def test_different_seeds_diverge(self) -> None:
        """Different seeds must produce different draws (sanity check)."""
        apply_seeds(1)
        a = random.random()
        apply_seeds(2)
        b = random.random()
        assert a != b

    def test_pythonhashseed_set(self) -> None:
        """``apply_seeds`` exports ``PYTHONHASHSEED`` for child processes."""
        apply_seeds(42)
        # ``setdefault`` was used; once set it stays. Just verify presence.
        assert "PYTHONHASHSEED" in os.environ


class TestStableHash:
    """``stable_hash`` is the cross-process replacement for ``hash()``."""

    def test_deterministic(self) -> None:
        """Same input → same output, every call."""
        assert stable_hash("BRCA1") == stable_hash("BRCA1")

    def test_different_inputs_diverge(self) -> None:
        """Two distinct strings produce different hashes."""
        assert stable_hash("BRCA1") != stable_hash("BRCA2")

    def test_known_value(self) -> None:
        """The known fixed value for 'geno_agent' captured during the demo run."""
        # If this changes, the chunk-id derivation has been perturbed.
        # See reports/visual_report.html, section "stable_hash".
        assert stable_hash("geno_agent") == 11547620462806487235

    def test_returns_int(self) -> None:
        """Always returns a non-negative 64-bit-fitting integer."""
        h = stable_hash("anything")
        assert isinstance(h, int)
        assert 0 <= h < 2**64

    def test_matches_blake2b_8_bytes(self) -> None:
        """Implementation should be ``blake2b(s, digest_size=8)`` big-endian."""
        s = "test-string-42"
        expected = int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "big")
        assert stable_hash(s) == expected
