"""Diff two replay runs (pure functions over the captured output documents)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

#: Relative tolerance below which two numbers count as identical.
REL_TOL = 1e-6
ABS_TOL = 1e-9
#: How many (node, key) series are returned for charting.
MAX_SERIES = 8
#: Max points per series (downsampled evenly beyond this).
MAX_SERIES_POINTS = 1500


def _is_num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _same(a: Any, b: Any) -> bool:
    if _is_num(a) and _is_num(b):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=ABS_TOL)
    return a == b


def _pct(a: float, b: float) -> Optional[float]:
    if a == 0:
        return None if b == 0 else math.inf
    return (b - a) / abs(a) * 100.0


def _json_pct(value: Optional[float]) -> Optional[float]:
    """JSON cannot carry inf — report 'infinite' change as None with a flag elsewhere."""
    if value is None or math.isinf(value):
        return None
    return value


def _by_frame(frames: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Last record per frame index (a node may emit more than once per frame)."""
    return {rec["frame"]: rec for rec in frames}


def _diff_values(a: Any, b: Any) -> Dict[str, Any]:
    entry: Dict[str, Any] = {"a": a, "b": b}
    if _is_num(a) and _is_num(b):
        entry["delta"] = b - a
        entry["pct"] = _json_pct(_pct(a, b))
    return entry


def _compare_node(a_frames: List[Dict[str, Any]], b_frames: List[Dict[str, Any]]):
    fa, fb = _by_frame(a_frames), _by_frame(b_frames)
    common = sorted(set(fa) & set(fb))
    keys: Dict[str, Dict[str, Any]] = {}
    series_src: Dict[str, List[Tuple[int, Any, Any]]] = {}

    def key_stats(key: str) -> Dict[str, Any]:
        return keys.setdefault(key, {
            "compared": 0, "differing": 0, "only_a": 0, "only_b": 0,
            "numeric": True, "sum_a": 0.0, "sum_b": 0.0, "n_num": 0, "max_abs_delta": 0.0,
        })

    for frame in common:
        va, vb = fa[frame]["values"], fb[frame]["values"]
        for key in set(va) | set(vb):
            st = key_stats(key)
            in_a, in_b = key in va, key in vb
            if in_a and not in_b:
                st["only_a"] += 1
                continue
            if in_b and not in_a:
                st["only_b"] += 1
                continue
            st["compared"] += 1
            x, y = va[key], vb[key]
            if _is_num(x) and _is_num(y):
                st["n_num"] += 1
                st["sum_a"] += x
                st["sum_b"] += y
                st["max_abs_delta"] = max(st["max_abs_delta"], abs(y - x))
                series_src.setdefault(key, []).append((frame, x, y))
            else:
                st["numeric"] = False
            if not _same(x, y):
                st["differing"] += 1

    key_rows: Dict[str, Dict[str, Any]] = {}
    for key, st in keys.items():
        row: Dict[str, Any] = {
            "compared": st["compared"], "differing": st["differing"],
            "only_a": st["only_a"], "only_b": st["only_b"],
        }
        if st["n_num"]:
            mean_a, mean_b = st["sum_a"] / st["n_num"], st["sum_b"] / st["n_num"]
            row.update({
                "mean_a": mean_a, "mean_b": mean_b, "mean_delta": mean_b - mean_a,
                "mean_pct": _json_pct(_pct(mean_a, mean_b)),
                "max_abs_delta": st["max_abs_delta"],
            })
        key_rows[key] = row

    point_diffs = [
        fb[f]["points"] - fa[f]["points"]
        for f in common
        if fa[f]["points"] is not None and fb[f]["points"] is not None
    ]
    node_row = {
        "emitted_a": len(a_frames),
        "emitted_b": len(b_frames),
        "frames_only_a": len(set(fa) - set(fb)),
        "frames_only_b": len(set(fb) - set(fa)),
        "frames_compared": len(common),
        "points_mean_delta": (sum(point_diffs) / len(point_diffs)) if point_diffs else None,
        "points_differing_frames": sum(1 for d in point_diffs if d != 0),
        "values": key_rows,
    }
    return node_row, series_src


def _downsample(rows: List[Tuple[int, Any, Any]]) -> List[Dict[str, Any]]:
    if len(rows) > MAX_SERIES_POINTS:
        step = len(rows) / MAX_SERIES_POINTS
        rows = [rows[int(i * step)] for i in range(MAX_SERIES_POINTS)]
    return [{"frame": f, "a": x, "b": y} for f, x, y in rows]


def _compare_saved_results(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pair saved results per node by order of creation and diff their metadata."""
    def group(items):
        out: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            out.setdefault(item["node_id"], []).append(item)
        return out

    ga, gb = group(a), group(b)
    per_node: Dict[str, Any] = {}
    for node_id in sorted(set(ga) | set(gb)):
        la, lb = ga.get(node_id, []), gb.get(node_id, [])
        pairs = []
        for idx in range(max(len(la), len(lb))):
            ra = la[idx] if idx < len(la) else None
            rb = lb[idx] if idx < len(lb) else None
            fields: Dict[str, Any] = {}
            va = ra["values"] if ra else {}
            vb = rb["values"] if rb else {}
            for key in sorted(set(va) | set(vb)):
                x, y = va.get(key), vb.get(key)
                if ra and rb and _same(x, y):
                    continue
                fields[key] = _diff_values(x, y)
            pairs.append({
                "index": idx,
                "frame_a": ra["frame"] if ra else None,
                "frame_b": rb["frame"] if rb else None,
                "status_a": ra["status"] if ra else None,
                "status_b": rb["status"] if rb else None,
                "fields": fields,
            })
        per_node[node_id] = {
            "count_a": len(la),
            "count_b": len(lb),
            "differing": sum(1 for p in pairs if p["fields"]),
            "pairs": pairs,
        }
    return per_node


def compare_runs(doc_a: Dict[str, Any], doc_b: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two output documents (as written by ``ReplayService``)."""
    nodes_a, nodes_b = doc_a["nodes"], doc_b["nodes"]
    nodes: Dict[str, Any] = {}
    series_candidates: List[Tuple[float, str, str, List[Tuple[int, Any, Any]]]] = []

    for node_id in sorted(set(nodes_a) | set(nodes_b)):
        na, nb = nodes_a.get(node_id), nodes_b.get(node_id)
        row, series_src = _compare_node(
            na["frames"] if na else [], nb["frames"] if nb else []
        )
        info = na or nb
        row["name"], row["type"] = info["name"], info["type"]
        row["in_a"], row["in_b"] = na is not None, nb is not None
        nodes[node_id] = row
        for key, rows in series_src.items():
            stats = row["values"][key]
            if stats["differing"]:
                series_candidates.append((stats["max_abs_delta"], node_id, key, rows))

    series_candidates.sort(key=lambda c: c[0], reverse=True)
    series = [
        {"node_id": nid, "node_name": nodes[nid]["name"], "key": key, "points": _downsample(rows)}
        for _, nid, key, rows in series_candidates[:MAX_SERIES]
    ]

    saved = _compare_saved_results(doc_a.get("saved_results", []), doc_b.get("saved_results", []))
    differing_values = sum(
        1 for n in nodes.values() for v in n["values"].values() if v["differing"]
    )
    summary = {
        "nodes_compared": len(nodes),
        "nodes_only_a": [i for i, n in nodes.items() if n["in_a"] and not n["in_b"]],
        "nodes_only_b": [i for i, n in nodes.items() if n["in_b"] and not n["in_a"]],
        "differing_value_keys": differing_values,
        "saved_results_a": sum(s["count_a"] for s in saved.values()),
        "saved_results_b": sum(s["count_b"] for s in saved.values()),
        "saved_results_differing": sum(s["differing"] for s in saved.values()),
        "errors_a": len(doc_a.get("errors", [])),
        "errors_b": len(doc_b.get("errors", [])),
        "identical": (
            differing_values == 0
            and all(
                n["frames_only_a"] == 0 and n["frames_only_b"] == 0
                and n["points_differing_frames"] == 0
                for n in nodes.values()
            )
            and all(s["differing"] == 0 and s["count_a"] == s["count_b"] for s in saved.values())
            and not summary_has_node_mismatch(nodes)
        ),
    }
    return {
        "run_a": doc_a.get("run_id"),
        "run_b": doc_b.get("run_id"),
        "summary": summary,
        "nodes": nodes,
        "saved_results": saved,
        "series": series,
        "errors": {"a": doc_a.get("errors", []), "b": doc_b.get("errors", [])},
    }


def summary_has_node_mismatch(nodes: Dict[str, Any]) -> bool:
    return any(not (n["in_a"] and n["in_b"]) for n in nodes.values())
