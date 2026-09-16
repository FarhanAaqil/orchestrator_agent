#!/usr/bin/env python3
"""
eval/render_confusion_matrix.py

Reads the latest eval results file from eval/results/ and prints a
formatted confusion matrix to stdout.

Usage:
    python eval/render_confusion_matrix.py
    python eval/render_confusion_matrix.py --file eval/results/20260917T120000Z.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_RESULTS_DIR = Path(__file__).parent / "results"
_SHORT = {
    "career_agent": "career",
    "research_agent": "research",
    "growth_content_agent": "growth",
    "critic_agent": "critic",
    "none": "none",
}


def load_latest() -> dict:
    files = sorted(_RESULTS_DIR.glob("*.json"))
    if not files:
        print("No result files found in eval/results/. Run eval/run_eval.py first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(files[-1].read_text())


def render(matrix: dict[str, dict[str, int]], agents: list[str]) -> None:
    short = {a: _SHORT.get(a, a[:7]) for a in agents}
    col_w = 10

    header = f"{'':>10}" + "".join(f"{short[a]:>{col_w}}" for a in agents) + f"{'none':>{col_w}}"
    print(header)
    print("-" * len(header))

    for exp in agents:
        row_label = f"{short[exp]:>10}"
        row_vals = ""
        for pred in agents:
            count = matrix.get(exp, {}).get(pred, 0)
            row_vals += f"{count:>{col_w}}"
        none_count = matrix.get(exp, {}).get("none", 0)
        row_vals += f"{none_count:>{col_w}}"
        print(row_label + row_vals)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=None, help="Path to results JSON (default: latest)")
    args = parser.parse_args()

    if args.file:
        data = json.loads(Path(args.file).read_text())
    else:
        data = load_latest()

    matrix = data["metrics"]["confusion_matrix"]
    agents = list(matrix.keys())

    run_at = data.get("run_at", "unknown")
    accuracy = data["metrics"]["accuracy"]
    correct = data["metrics"]["correct"]
    total = data["metrics"]["total"]

    print(f"\nEval run: {run_at}")
    print(f"Accuracy: {accuracy:.1%}  ({correct}/{total})\n")
    print("Confusion Matrix (rows=expected, cols=predicted):\n")
    render(matrix, agents)
    print()


if __name__ == "__main__":
    main()
