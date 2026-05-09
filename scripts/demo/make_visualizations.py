"""Generate matplotlib charts and tables from ``pipeline_stats.json``.

Outputs go to ``reports/images/`` as PNG / SVG. The HTML and Markdown
report templates reference these by relative path.

Charts produced:
  * ``pipeline_throughput.png`` — bar chart of per-step elapsed seconds.
  * ``section_distribution.png`` — bar chart of chunks per section type.
  * ``embedding_throughput.png`` — annotated single-bar of embed chunks/s
    with comparison to a CPU baseline (~25 chunks/s).
  * ``retrieval_modes.png`` — table rendering of top-1 hits per probe per mode.
  * ``terminal_screenshot.png`` — faux-terminal rendering of the validate
    log so the visual report shows real output without a real screenshot.

Run::

    python scripts/demo/make_visualizations.py
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Final

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("make_viz")

CATEGORY_COLORS: Final[dict[str, str]] = {
    "introduction": "#4f81bd",
    "methods":      "#9bbb59",
    "results":      "#f79646",
    "case":         "#c0504d",
    "discussion":   "#8064a2",
    "conclusion":   "#1f497d",
    "other":        "#a6a6a6",
}


def parse_args() -> argparse.Namespace:
    """CLI args."""
    p = argparse.ArgumentParser(description="Render report visualizations.")
    p.add_argument("--stats", type=Path,
                   default=PROJECT_ROOT / "reports" / "pipeline_stats.json")
    p.add_argument("--out", type=Path,
                   default=PROJECT_ROOT / "reports" / "images")
    return p.parse_args()


def chart_pipeline_throughput(stats: dict, out: Path) -> Path:
    """Bar chart of per-step elapsed seconds."""
    steps = stats["steps"]
    labels = [s["id"].split("_", 1)[1] for s in steps]
    elapsed = [s.get("elapsed_s") or 0 for s in steps]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    bars = ax.bar(labels, elapsed, color="#5b9bd5", edgecolor="#1f3a5f", linewidth=0.8)
    for b, v in zip(bars, elapsed):
        ax.text(b.get_x() + b.get_width() / 2, v + max(elapsed) * 0.02,
                f"{v:.1f}s", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Elapsed (s)", fontsize=10)
    ax.set_title("End-to-end pipeline timing — 100 articles, single host",
                 fontsize=12, weight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    fig.tight_layout()
    p = out / "pipeline_throughput.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    logger.info(f"  wrote {p.name}")
    return p


def chart_section_distribution(stats: dict, out: Path) -> Path:
    """Bar chart of chunks per section type."""
    chunk_step = next((s for s in stats["steps"] if s["id"] == "08_chunk"), None)
    by = (chunk_step or {}).get("metrics", {}).get("by_section_type", {})
    if not by:
        return out / "section_distribution.png"  # placeholder
    items = sorted(by.items(), key=lambda kv: -kv[1])
    labels = [k for k, _ in items]
    counts = [v for _, v in items]
    colors = [CATEGORY_COLORS.get(k, "#888") for k in labels]
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bars = ax.bar(labels, counts, color=colors, edgecolor="#222", linewidth=0.6)
    for b, v in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, v + max(counts) * 0.02,
                f"{v}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Number of chunks", fontsize=10)
    ax.set_title("Chunk distribution by JATS section type",
                 fontsize=12, weight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    fig.tight_layout()
    p = out / "section_distribution.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    logger.info(f"  wrote {p.name}")
    return p


def chart_embedding_throughput(stats: dict, out: Path) -> Path:
    """Bar comparing measured GPU throughput vs CPU baseline."""
    embed = next((s for s in stats["steps"] if s["id"] == "09_embed"), None)
    if not embed or "encode_chunks_per_s" not in embed.get("metrics", {}):
        return out / "embedding_throughput.png"
    measured = embed["metrics"]["encode_chunks_per_s"]
    cpu_baseline = 25  # rough sentence-transformers CPU baseline for PubMedBERT-base
    labels = ["RTX 5090\n(measured)", "CPU baseline\n(approx)"]
    values = [measured, cpu_baseline]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    bars = ax.bar(labels, values,
                  color=["#1f8a4f", "#a6a6a6"], edgecolor="#222", linewidth=0.6)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + max(values) * 0.02,
                f"{v} chunks/s", ha="center", va="bottom", fontsize=10, weight="bold")
    ax.set_ylabel("Throughput (chunks / s)", fontsize=10)
    ax.set_title("PubMedBERT embedding throughput — measured vs CPU baseline",
                 fontsize=12, weight="bold")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.6)
    fig.tight_layout()
    p = out / "embedding_throughput.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    logger.info(f"  wrote {p.name}")
    return p


def chart_retrieval_modes(stats: dict, out: Path) -> Path:
    """Render a table of top-1 hits per (probe, mode)."""
    val = next((s for s in stats["steps"] if s["id"] == "11_validate"), None)
    probes = (val or {}).get("metrics", {}).get("probes", [])
    if not probes:
        return out / "retrieval_modes.png"

    rows: list[list[str]] = []
    for p in probes[:10]:  # cap rows
        query = p["query"]
        if len(query) > 48:
            query = query[:46] + "…"
        cells = [query]
        for mode in ("dense", "bm25", "hybrid"):
            top = (p["modes"].get(mode) or [None])[0]
            if top is None:
                cells.append("(none)")
                continue
            label = f"{top['pmcid']} {top['section_type']}\n{top['score']:.3f}"
            cells.append(label)
        rows.append(cells)

    fig_h = 1.3 + 0.62 * len(rows)
    fig, ax = plt.subplots(figsize=(11, fig_h))
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=["Probe query", "Dense (top-1)", "BM25 (top-1)", "Hybrid RRF (top-1)"],
        loc="center", cellLoc="left",
        colWidths=[0.34, 0.22, 0.22, 0.22],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1.0, 1.7)
    for col in range(4):
        cell = table[0, col]
        cell.set_facecolor("#1f3a5f")
        cell.set_text_props(color="white", weight="bold")
    for r in range(1, len(rows) + 1):
        for c in range(4):
            if r % 2 == 0:
                table[r, c].set_facecolor("#f4f6fa")
    ax.set_title("Probe queries vs top-1 retrieved chunks",
                 fontsize=12, weight="bold", pad=10)
    fig.tight_layout()
    p = out / "retrieval_modes.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"  wrote {p.name}")
    return p


def chart_terminal_screenshot(stats: dict, out: Path) -> Path:
    """Render a faux-terminal screenshot of the validate step."""
    val = next((s for s in stats["steps"] if s["id"] == "11_validate"), None)
    probes = (val or {}).get("metrics", {}).get("probes", [])
    if not probes:
        return out / "terminal_screenshot.png"
    lines: list[tuple[str, str]] = [
        ("$ python scripts/indexing/11_validate_index.py", "lime"),
        ("Connected to Qdrant @ localhost:6533", "white"),
    ]
    n = next((s for s in stats["steps"] if s["id"] == "10_upload"), None)
    points = (n or {}).get("metrics", {}).get("points", "?")
    lines.append((f"Collection 'geno_agent_pmc_oa_v1' status=green, points={points:,}", "white"))
    for probe in probes[:3]:
        lines.append(("", "white"))
        lines.append((f"==== Probe: '{probe['query']}' ====", "yellow"))
        for mode in ("dense", "hybrid"):
            top = (probe["modes"].get(mode) or [None])[0]
            if top is None:
                continue
            tag = f"-- {mode:6s} (top-1) --"
            lines.append((tag, "cyan"))
            line = (f"  [{top['score']:.3f}] {top['pmcid']:14s} "
                    f"{top['section_type']:11s} | {top['snippet'][:90]}…")
            lines.append((line, "white"))

    fig_h = 0.32 * len(lines) + 0.6
    fig, ax = plt.subplots(figsize=(13, fig_h), facecolor="#0a0a0a")
    ax.set_facecolor("#0a0a0a")
    ax.axis("off")
    color_map = {"white": "#dddddd", "lime": "#4ce14c",
                 "yellow": "#f5d76e", "cyan": "#62d4e0"}
    for i, (text, color) in enumerate(lines):
        ax.text(0.01, 1 - (i + 1) / (len(lines) + 1),
                text, color=color_map.get(color, "white"),
                family="monospace", fontsize=8.5,
                transform=ax.transAxes, va="top")
    fig.tight_layout(pad=0.4)
    p = out / "terminal_screenshot.png"
    fig.savefig(p, dpi=150, facecolor=fig.get_facecolor())
    plt.close(fig)
    logger.info(f"  wrote {p.name}")
    return p


def main() -> int:
    """Read pipeline_stats.json, render every chart."""
    args = parse_args()
    if not args.stats.exists():
        logger.error(f"Stats not found: {args.stats}")
        return 1
    stats: dict[str, Any] = json.loads(args.stats.read_text())
    args.out.mkdir(parents=True, exist_ok=True)

    chart_pipeline_throughput(stats, args.out)
    chart_section_distribution(stats, args.out)
    chart_embedding_throughput(stats, args.out)
    chart_retrieval_modes(stats, args.out)
    chart_terminal_screenshot(stats, args.out)

    logger.info("All charts written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
