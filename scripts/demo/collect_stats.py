"""Parse the captured pipeline run logs into a single ``pipeline_stats.json``.

Reads ``reports/run_logs/*.log`` produced by ``run_pipeline.sh``,
extracts step-level numbers (counts, durations, throughput), and writes
a structured JSON file that ``make_visualizations.py`` and the report
templates consume.

Run::

    python scripts/demo/collect_stats.py
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("collect_stats")


@dataclass
class StepStats:
    """Per-step parsed statistics."""

    id: str
    desc: str
    log_path: str
    elapsed_s: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)


def _grep_n(log: Path, pattern: str, group: int = 1) -> str | None:
    """Return the first regex group match in ``log``."""
    rx = re.compile(pattern)
    for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = rx.search(line)
        if m:
            return m.group(group)
    return None


def parse_fetch(log: Path) -> dict[str, Any]:
    """Extract counts from 01_fetch.log."""
    out: dict[str, Any] = {}
    out["total_files"] = int(_grep_n(log, r"total files:\s+(\d+)") or 0)
    size = _grep_n(log, r"total size:\s+([\d.]+)\s*MB")
    if size:
        out["total_size_mb"] = float(size)
    cats = re.findall(r"(\w+):\s+downloaded\s+(\d+)", log.read_text(errors="ignore"))
    if cats:
        out["per_category"] = {k: int(v) for k, v in cats}
    return out


def parse_parse(log: Path) -> dict[str, Any]:
    """Extract counts from 06_parse.log."""
    out: dict[str, Any] = {}
    parsed = _grep_n(log, r"parsed:\s+(\d+)/(\d+)", group=1)
    total = _grep_n(log, r"parsed:\s+(\d+)/(\d+)", group=2)
    out["parsed"] = int(parsed) if parsed else 0
    out["input_total"] = int(total) if total else 0
    out["sections"] = int(_grep_n(log, r"total sections:\s*(\d+)") or 0)
    out["chars"] = int((_grep_n(log, r"total chars:\s+([\d,]+)") or "0").replace(",", ""))
    return out


def parse_filter(log: Path) -> dict[str, Any]:
    """Extract counts from 07_filter.log."""
    out: dict[str, Any] = {}
    out["input"] = int(_grep_n(log, r"total in:\s+(\d+)") or 0)
    retained = _grep_n(log, r"retained:\s+(\d+)\s*\(([\d.]+)%\)")
    if retained:
        out["retained"] = int(retained)
    pct = _grep_n(log, r"retained:\s+\d+\s*\(([\d.]+)%\)")
    if pct:
        out["retained_pct"] = float(pct)
    out["rejected"] = int(_grep_n(log, r"rejected:\s+(\d+)") or 0)
    return out


def parse_chunk(log: Path) -> dict[str, Any]:
    """Extract counts from 08_chunk.log."""
    out: dict[str, Any] = {}
    out["articles_in"] = int(_grep_n(log, r"articles in:\s+(\d+)") or 0)
    out["chunks_out"] = int(_grep_n(log, r"chunks out:\s+(\d+)") or 0)
    out["short_skipped"] = int(_grep_n(log, r"short sections skipped:\s+(\d+)") or 0)
    by = _grep_n(log, r"by section_type:\s+(\{[^}]+\})")
    if by:
        with contextlib.suppress(SyntaxError, NameError, ValueError):
            out["by_section_type"] = eval(by, {"__builtins__": {}})
    return out


def parse_embed(log: Path) -> dict[str, Any]:
    """Extract counts from 09_embed.log."""
    out: dict[str, Any] = {}
    out["records"] = int((_grep_n(log, r"records:\s+([\d,]+)") or "0").replace(",", ""))
    enc = _grep_n(log, r"Encoded ([\d,]+) chunks in ([\d.]+)s\s+\(([\d]+)\s+chunks/s")
    if enc:
        out["encode_seconds"] = float(_grep_n(log, r"Encoded [\d,]+ chunks in ([\d.]+)s") or 0)
        out["encode_chunks_per_s"] = int(_grep_n(log, r"\(([\d]+)\s+chunks/s") or 0)
    out["parquet_size_mb"] = float(_grep_n(log, r"\(([\d.]+)\s+MB,\s+zstd\)") or 0.0)
    return out


def parse_upload(log: Path) -> dict[str, Any]:
    """Extract counts from 10_upload.log."""
    out: dict[str, Any] = {}
    out["points"] = int(
        (_grep_n(log, r"Upload complete:\s+([\d,]+)\s+points") or "0").replace(",", "")
    )
    return out


def parse_validate(log: Path) -> dict[str, Any]:
    """Extract probe results from 11_validate.log."""
    text = log.read_text(encoding="utf-8", errors="ignore")
    probes: list[dict[str, Any]] = []
    current_probe: dict[str, Any] | None = None
    current_mode: str | None = None
    for line in text.splitlines():
        m = re.search(r"==== Probe:\s+'([^']+)'\s+====", line)
        if m:
            if current_probe:
                probes.append(current_probe)
            current_probe = {"query": m.group(1), "modes": {}}
            current_mode = None
            continue
        m = re.search(r"--\s+(dense|bm25|hybrid)\s+\(top\s+(\d+)\)", line)
        if m and current_probe is not None:
            current_mode = m.group(1).strip()
            current_probe["modes"][current_mode] = []
            continue
        m = re.search(r"\[\s*([\d.]+)\]\s+(PMC\d+)\s+(\w+)\s+\|\s+(.+)$", line)
        if m and current_probe is not None and current_mode is not None:
            current_probe["modes"][current_mode].append(
                {
                    "score": float(m.group(1)),
                    "pmcid": m.group(2),
                    "section_type": m.group(3),
                    "snippet": m.group(4)[:240].rstrip("…").strip(),
                }
            )
    if current_probe:
        probes.append(current_probe)
    return {"probes": probes, "n_probes": len(probes)}


def step_elapsed_seconds(log: Path) -> float | None:
    """Read first and last log timestamp and compute elapsed seconds."""
    text = log.read_text(encoding="utf-8", errors="ignore").splitlines()
    rx = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+")
    stamps: list[str] = []
    for line in text:
        m = rx.match(line)
        if m:
            stamps.append(m.group(1))
            if len(stamps) >= 2:
                break
    last_stamps: list[str] = []
    for line in reversed(text):
        m = rx.match(line)
        if m:
            last_stamps.append(m.group(1))
            break
    if not stamps or not last_stamps:
        return None
    from datetime import datetime

    fmt = "%Y-%m-%d %H:%M:%S"
    return (
        datetime.strptime(last_stamps[0], fmt) - datetime.strptime(stamps[0], fmt)
    ).total_seconds()


PARSERS: Final[dict[str, tuple[str, callable]]] = {
    "01_fetch": ("Fetch demo corpus (NCBI esearch + efetch)", parse_fetch),
    "06_parse": ("Parse JATS XML", parse_parse),
    "07_filter": ("Filter genetics / rare disease", parse_filter),
    "08_chunk": ("UUID5 section-aware chunking", parse_chunk),
    "09_embed": ("PubMedBERT embedding (RTX 5090)", parse_embed),
    "10_upload": ("Qdrant upload (dense + BM25)", parse_upload),
    "11_validate": ("Hybrid retrieval probes", parse_validate),
}


def parse_args() -> argparse.Namespace:
    """CLI args."""
    p = argparse.ArgumentParser(description="Parse run logs to JSON stats.")
    p.add_argument("--logs", type=Path, default=PROJECT_ROOT / "reports" / "run_logs")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports" / "pipeline_stats.json")
    return p.parse_args()


def collect_env_metadata() -> dict[str, Any]:
    """Collect host environment fingerprints (Python, GPU, Qdrant, git rev)."""
    out: dict[str, Any] = {}
    with contextlib.suppress(subprocess.CalledProcessError):
        out["python"] = subprocess.check_output(["python", "--version"], text=True).strip()
    with contextlib.suppress(subprocess.CalledProcessError):
        out["git_rev"] = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    try:
        import torch

        out["torch"] = torch.__version__
        out["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            out["gpu"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return out


def main() -> int:
    """Parse all known logs into a single stats JSON."""
    args = parse_args()
    if not args.logs.exists():
        logger.error(f"Log dir not found: {args.logs}")
        return 1

    steps: list[StepStats] = []
    for step_id, (desc, parser) in PARSERS.items():
        log_path = args.logs / f"{step_id}.log"
        if not log_path.exists():
            logger.warning(f"  missing log: {log_path.name}")
            continue
        s = StepStats(id=step_id, desc=desc, log_path=str(log_path.relative_to(PROJECT_ROOT)))
        s.elapsed_s = step_elapsed_seconds(log_path)
        try:
            s.metrics = parser(log_path)
        except (re.error, ValueError, OSError) as exc:
            logger.warning(f"  {step_id}: parser error {type(exc).__name__}: {exc}")
        steps.append(s)
        logger.info(f"  {step_id}: elapsed={s.elapsed_s} | {len(s.metrics)} metrics")

    payload: dict[str, Any] = {
        "env": collect_env_metadata(),
        "steps": [asdict(s) for s in steps],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
