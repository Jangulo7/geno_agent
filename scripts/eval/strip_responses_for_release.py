"""Strip verbatim PMC-OA text from raw LLM response dumps for license-clean release.

The per-case ``cell_*_responses`` JSONs embed verbatim PMC-OA full-text passages
(``retrieved_per_gene[].text``, ``lea_evidence_per_gene[].text`` and the
``lea_user_prompt`` built from them). Those passages span mixed CC license tiers
and cannot be publicly redistributed (the same blocker as the corpus/index).

This tool produces a publishable derivative that keeps only the project's own
AGPL-licensed model output (rankings, rationales, confidences, our prompt
templates) plus chunk *provenance* (``chunk_id``, ``source_pmcid``,
``section_type``, retrieval scores) — never the passage text itself. The result
is a license-clean explainability artifact suitable for Figshare.

Example:
    python scripts/eval/strip_responses_for_release.py \\
        --input data/eval_1050/cell_S_responses \\
        --output figshare_uploads/_staging/paper-genoagent/rationale_derivative
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Keys whose values are (or may contain) verbatim PMC-OA passage text. They are
# removed everywhere they occur in the response tree.
_TEXT_KEYS: frozenset[str] = frozenset({"text", "lea_user_prompt"})


def strip_pmc_text(obj: Any) -> Any:
    """Recursively drop verbatim-passage keys from a decoded JSON value.

    Args:
        obj: A JSON-decoded value (dict, list, or scalar).

    Returns:
        A new value with every key in ``_TEXT_KEYS`` removed at any depth. All
        other content (model output, provenance IDs, scores) is preserved.
    """
    if isinstance(obj, dict):
        return {key: strip_pmc_text(value) for key, value in obj.items() if key not in _TEXT_KEYS}
    if isinstance(obj, list):
        return [strip_pmc_text(item) for item in obj]
    return obj


def process_file(src: Path, dst: Path) -> int:
    """Strip one response JSON and write the derivative.

    Args:
        src: Path to the raw response JSON.
        dst: Path to write the stripped JSON to.

    Returns:
        The number of verbatim-text fields removed from this file.
    """
    raw = src.read_text(encoding="utf-8")
    before = sum(raw.count(f'"{key}"') for key in _TEXT_KEYS)
    stripped = strip_pmc_text(json.loads(raw))
    dst.write_text(json.dumps(stripped, ensure_ascii=False, indent=2), encoding="utf-8")
    return before


def main() -> None:
    """Parse arguments and strip every JSON in the input directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="dir of raw response JSONs")
    parser.add_argument("--output", type=Path, required=True, help="dir for stripped JSONs")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args.output.mkdir(parents=True, exist_ok=True)

    files = sorted(args.input.glob("*.json"))
    if not files:
        logger.warning("no JSON files found in %s", args.input)
        return

    total_stripped = 0
    for src in files:
        total_stripped += process_file(src, args.output / src.name)

    # Verification: the output must contain none of the dropped keys.
    leaked = sum(
        out.read_text(encoding="utf-8").count(f'"{key}"')
        for out in args.output.glob("*.json")
        for key in _TEXT_KEYS
    )
    logger.info(
        "stripped %d files, removed %d verbatim-text fields; residual keys in output: %d",
        len(files),
        total_stripped,
        leaked,
    )
    if leaked:
        raise RuntimeError(f"{leaked} verbatim-text keys remain in output — aborting")


if __name__ == "__main__":
    main()
