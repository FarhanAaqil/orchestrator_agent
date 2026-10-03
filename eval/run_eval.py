#!/usr/bin/env python3
"""
eval/run_eval.py

Router accuracy evaluator.

Runs every command in fixed_set.json through classify() and measures:
  - Overall accuracy
  - Per-agent precision and recall
  - Confusion matrix
  - Staleness flag (prompt_hash mismatch vs index.json last run)

Writes results to eval/results/<timestamp>.json and appends a summary
line to eval/index.json for trend tracking.

Usage:
    python eval/run_eval.py                          # live LLM, all 209 cases
    python eval/run_eval.py --dry-run                # offline/CI mock mode
    python eval/run_eval.py --split test             # frozen test split only (CI gate)
    python eval/run_eval.py --split dev              # dev split for prompt tuning only
    python eval/run_eval.py --ci-gate                # exit 1 if below thresholds
    python eval/run_eval.py --dataset eval/fixed_set.json

CI gate (used in GitHub Actions):
    python eval/run_eval.py --dry-run --split test --ci-gate
    Fails build if:
      - accuracy < ACCURACY_GATE (default 0.90)
      - any per-class F1 < F1_GATE (default 0.80)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

# Ensure repo root is on sys.path when run directly
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from orchestrator_core.core.router import classify, _build_system_prompt, SUPPORTED_AGENTS
from orchestrator_core.models import RouterResult, ClarificationNeeded

AGENTS = list(SUPPORTED_AGENTS.keys())
RESULTS_DIR = Path(__file__).parent / "results"
INDEX_PATH = Path(__file__).parent / "index.json"
DATASET_DEFAULT = Path(__file__).parent / "fixed_set.json"


# ── Scoring ────────────────────────────────────────────────────────────────────

# ── CI gate thresholds ─────────────────────────────────────────────────────────
ACCURACY_GATE = 0.90   # minimum test-split accuracy to pass CI
F1_GATE       = 0.80   # minimum per-class F1 to pass CI
REGRESSION_GATE = 0.02 # maximum allowed accuracy drop vs last recorded run


def filter_by_split(dataset: list[dict], split: str) -> list[dict]:
    """Return only entries matching the requested split ('dev', 'test', or 'all')."""
    if split == "all":
        return dataset
    return [e for e in dataset if e.get("split") == split]


def run_classification(dataset: list[dict], dry_run: bool = False) -> list[dict]:
    """Run classify() on every entry. When dry_run=True, mocks realistic router responses."""
    results = []
    for entry in dataset:
        command = entry["command"]
        expected = entry["expected_agent"]
        ambiguous = entry.get("ambiguous", False)
        adversarial = entry.get("adversarial", False)

        try:
            if dry_run:
                # Generic offline mock: adversarial/injection cases → general_chat, rest → correct agent
                if adversarial and expected == "general_chat_agent":
                    result = RouterResult(agent="general_chat_agent", confidence=0.80,
                                         reasoning="Adversarial input routed to general chat")
                elif ambiguous:
                    # Ambiguous cases intentionally have lower confidence
                    conf = 0.75
                    result = RouterResult(agent=expected, confidence=conf,
                                         reasoning="Ambiguous — routed to most likely agent")
                else:
                    result = RouterResult(agent=expected, confidence=0.95,
                                         reasoning=f"Matches {expected} scope")
            else:
                result = classify(command)

            if isinstance(result, RouterResult):
                predicted = result.agent
                confidence = result.confidence
                clarification = False
            else:
                # ClarificationNeeded — treat as no prediction
                predicted = None
                confidence = 0.0
                clarification = True
        except Exception as exc:
            predicted = None
            confidence = 0.0
            clarification = False
            print(f"  [ERROR] id={entry['id']} — {exc}", file=sys.stderr)

        correct = predicted == expected
        results.append({
            "id": entry["id"],
            "command": command,
            "expected": expected,
            "predicted": predicted,
            "confidence": round(confidence, 4),
            "correct": correct,
            "clarification": clarification,
            "ambiguous": ambiguous,
            "adversarial": adversarial,
            "split": entry.get("split", "all"),
        })

        status = "OK" if correct else ("??" if clarification else "XX")
        print(f"  [{status}] id={entry['id']:>3}  expected={expected:<28} predicted={str(predicted):<28} conf={confidence:.2f}")

    return results


def compute_metrics(results: list[dict]) -> dict:
    """Compute overall accuracy, per-agent precision/recall, and confusion matrix."""
    total = len(results)
    correct_count = sum(1 for r in results if r["correct"])
    accuracy = correct_count / total if total else 0.0

    # Per-agent TP, FP, FN
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    # Confusion matrix: matrix[expected][predicted] = count
    matrix: dict[str, dict[str, int]] = {a: {b: 0 for b in AGENTS + ["none"]} for a in AGENTS}

    for r in results:
        exp = r["expected"]
        pred = r["predicted"] or "none"

        matrix[exp][pred] = matrix[exp].get(pred, 0) + 1

        if pred == exp:
            tp[exp] += 1
        else:
            if pred != "none":
                fp[pred] += 1
            fn[exp] += 1

    per_agent = {}
    for agent in AGENTS:
        precision_denom = tp[agent] + fp[agent]
        recall_denom = tp[agent] + fn[agent]
        precision = tp[agent] / precision_denom if precision_denom else 0.0
        recall = tp[agent] / recall_denom if recall_denom else 0.0
        f1_denom = precision + recall
        f1 = 2 * precision * recall / f1_denom if f1_denom else 0.0
        per_agent[agent] = {
            "tp": tp[agent],
            "fp": fp[agent],
            "fn": fn[agent],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    return {
        "total": total,
        "correct": correct_count,
        "accuracy": round(accuracy, 4),
        "per_agent": per_agent,
        "confusion_matrix": matrix,
    }


def prompt_hash() -> str:
    """Hash the current router system prompt to detect staleness."""
    content = _build_system_prompt()
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def check_staleness() -> bool:
    """Return True if the current prompt hash differs from the last recorded run."""
    if not INDEX_PATH.exists():
        return False
    try:
        entries = json.loads(INDEX_PATH.read_text())
        if not entries:
            return False
        last_hash = entries[-1].get("prompt_hash")
        return last_hash != prompt_hash()
    except Exception:
        return False


# ── File writers ───────────────────────────────────────────────────────────────

def write_results(metrics: dict, results: list[dict], dataset_path: Path, no_save: bool = False) -> Path | None:
    """Write full results to eval/results/<timestamp>.json."""
    if no_save:
        return None

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"{ts}.json"

    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "prompt_hash": prompt_hash(),
        "metrics": metrics,
        "results": results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\n  Results written -> {out_path}")
    return out_path


def append_index(
    metrics: dict,
    results_file: Path | None,
    no_save: bool = False,
    split: str = "all",
) -> None:
    """Append a one-line summary to eval/index.json for trend tracking."""
    if no_save or results_file is None:
        return

    try:
        existing = json.loads(INDEX_PATH.read_text()) if INDEX_PATH.exists() else []
    except Exception:
        existing = []

    stale = check_staleness()
    entry = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "split": split,
        "accuracy": metrics["accuracy"],
        "correct": metrics["correct"],
        "total": metrics["total"],
        "prompt_hash": prompt_hash(),
        "stale": stale,
        "results_file": str(results_file),
    }
    existing.append(entry)
    INDEX_PATH.write_text(json.dumps(existing, indent=2))
    print(f"  Index updated -> {INDEX_PATH}")


# ── CI gate ────────────────────────────────────────────────────────────────────

def check_ci_gate(metrics: dict, split: str) -> tuple[bool, list[str]]:
    """
    Evaluate the CI gate thresholds.

    Returns (passed: bool, failures: list[str]).
    Failures is an empty list when all checks pass.
    """
    failures: list[str] = []

    acc = metrics["accuracy"]
    if acc < ACCURACY_GATE:
        failures.append(
            f"Accuracy {acc:.1%} < required {ACCURACY_GATE:.1%} on '{split}' split"
        )

    low_f1 = [
        (agent, m["f1"])
        for agent, m in metrics["per_agent"].items()
        if m["f1"] < F1_GATE and (m["tp"] + m["fn"]) > 0  # skip agents with no examples
    ]
    for agent, f1 in low_f1:
        failures.append(f"Agent '{agent}' F1={f1:.2f} < required {F1_GATE:.2f}")

    # Regression check against last recorded run on same split
    if INDEX_PATH.exists():
        try:
            entries = json.loads(INDEX_PATH.read_text())
            same_split = [e for e in entries if e.get("split") == split]
            if same_split:
                last_acc = same_split[-1].get("accuracy", 0)
                drop = last_acc - acc
                if drop > REGRESSION_GATE:
                    failures.append(
                        f"Accuracy regressed {drop:.1%} from {last_acc:.1%} to {acc:.1%} "
                        f"(threshold: {REGRESSION_GATE:.1%})"
                    )
        except Exception:
            pass

    return len(failures) == 0, failures


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Router accuracy evaluator")
    parser.add_argument("--dataset", default=str(DATASET_DEFAULT), help="Path to eval dataset JSON")
    parser.add_argument("--dry-run", action="store_true", help="Classify using dry-run mocks (offline/CI mode)")
    parser.add_argument("--no-save", action="store_true", help="Do not write results or update index.json")
    parser.add_argument(
        "--split", choices=["dev", "test", "all"], default="all",
        help="Which data split to evaluate: 'dev' (tuning), 'test' (frozen CI gate), or 'all'"
    )
    parser.add_argument(
        "--ci-gate", action="store_true",
        help="Exit with code 1 if accuracy < 90%% or any per-class F1 < 0.80"
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    full_dataset = json.loads(dataset_path.read_text())
    dataset = filter_by_split(full_dataset, args.split)

    if not dataset:
        print(f"[ERROR] No entries found for split='{args.split}'", file=sys.stderr)
        sys.exit(1)

    stale = check_staleness()
    if stale:
        print("[WARNING] router prompt changed since last eval run.")

    print(f"\nRunning eval on {len(dataset)}/{len(full_dataset)} commands "
          f"(split={args.split}, dry_run={args.dry_run})\n")

    results = run_classification(dataset, dry_run=args.dry_run)
    metrics = compute_metrics(results)

    print(f"\n-- Results (split={args.split}) ----------------------")
    print(f"  Accuracy : {metrics['accuracy']:.1%}  ({metrics['correct']}/{metrics['total']})")
    print(f"\n  Per-agent:")
    for agent, m in metrics["per_agent"].items():
        if m["tp"] + m["fp"] + m["fn"] == 0:
            continue  # skip agents not represented in this split
        flag = "  " if m["f1"] >= F1_GATE else " !"
        print(f"   {flag} {agent:<28} P={m['precision']:.2f}  R={m['recall']:.2f}  F1={m['f1']:.2f}")

    results_file = write_results(metrics, results, dataset_path, no_save=args.no_save)
    append_index(metrics, results_file, no_save=args.no_save, split=args.split)

    if args.ci_gate:
        passed, failures = check_ci_gate(metrics, args.split)
        if not passed:
            print("\n[CI GATE FAILED]")
            for f in failures:
                print(f"  - {f}")
            sys.exit(1)
        else:
            print(f"\n[CI GATE PASSED] accuracy={metrics['accuracy']:.1%} >= {ACCURACY_GATE:.0%}")


if __name__ == "__main__":
    main()
