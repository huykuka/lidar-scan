"""Score replay runs against ground-truth targets (pure functions)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def score_run(summary: Dict[str, Any], targets: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare a run's metric statistics with the targets of its recording.

    ``summary`` is the run summary (``summary["nodes"][node_id]["values"][key]`` holds
    count/min/max/mean/last and, for newer runs, std).  Status per target:

    * ``pass`` / ``fail`` — a tolerance is set and the mean error is within / beyond it
    * ``info``            — no tolerance, error is reported only
    * ``missing``         — the run did not produce that metric
    """
    nodes = (summary or {}).get("nodes") or {}
    scores: List[Dict[str, Any]] = []
    for target in targets:
        stats = ((nodes.get(target["node_id"]) or {}).get("values") or {}).get(target["metric_key"])
        entry: Dict[str, Any] = {
            "target_id": target["id"],
            "label": target.get("label") or target["metric_key"],
            "node_id": target["node_id"],
            "metric_key": target["metric_key"],
            "expected": target["expected"],
            "tolerance": target.get("tolerance"),
            "value": None, "std": None, "error": None, "abs_error": None,
            "pct_error": None, "status": "missing",
        }
        if stats and stats.get("count"):
            mean = float(stats["mean"])
            error = mean - float(target["expected"])
            tol: Optional[float] = target.get("tolerance")
            entry.update({
                "value": mean,
                "std": stats.get("std"),
                "error": error,
                "abs_error": abs(error),
                "pct_error": (error / abs(target["expected"]) * 100.0) if target["expected"] else None,
                "status": "info" if tol is None else ("pass" if abs(error) <= tol else "fail"),
            })
        scores.append(entry)
    return {"overall": overall_status(scores), "targets": scores}


def overall_status(scores: List[Dict[str, Any]]) -> Optional[str]:
    """One status for a whole run, or None when there is nothing to score."""
    if not scores:
        return None
    statuses = {s["status"] for s in scores}
    if "fail" in statuses:
        return "fail"
    if "missing" in statuses:
        return "missing"
    if statuses == {"info"}:
        return "info"
    return "pass"


def rank_key(score: Dict[str, Any]) -> float:
    """Sort key for 'closest to ground truth first' (sum of absolute errors, missing last)."""
    errors = [t["abs_error"] for t in score["targets"]]
    if not errors or any(e is None or math.isnan(e) for e in errors):
        return math.inf
    return float(sum(errors))
