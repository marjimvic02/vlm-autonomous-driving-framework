#!/usr/bin/env python3
"""
make_thesis_tables.py - build all Block C comparison tables for the thesis, in both
Markdown (paste into Word / preview) and LaTeX booktabs (paste into a LaTeX thesis).

Requires parse_runs.py in the same directory (it reuses its analysis logic).

Usage:
    python3 scripts/analysis/make_thesis_tables.py --dir DATA_ROOT --out-dir OUTPUT_DIR

Produces:
    <out-prefix>.md   all tables in Markdown
    <out-prefix>.tex  all tables in LaTeX (booktabs; needs \\usepackage{booktabs})
and prints a short summary to stdout.

File-name resolution is tolerant: for each (model, scenario) it tries several common
names for the .md and .log, so the freerun naming mismatch (2B_freerun.log vs
qwen_2B_freerun.md) is handled automatically.
"""

import os
import re
import argparse
from collections import Counter

from parse_runs import analyze_file, median

# (key, display name) in the order they were run
SCENARIOS = [
    ("freerun", "Free"),
    ("traffic", "Traffic"),
    ("obs_2", "Obstacle"),
    ("pedestrian", "Pedestrian"),
    ("ambulance", "Ambulance"),
]

# Column label -> list of filename stems to try (model side)
MODEL_STEMS = {
    "2B": ["qwen_2B_{sc}", "2B_{sc}"],
    "Haiku": ["haiku_{sc}"],
}

LOG_PATTERNS = {
    "stale": r"stale",
    "stop_override": r"overridden",
    "commitment": r"commitment active",
    "fallback": r"fallback action published",
}


def resolve(directory, stems, sc, ext):
    for stem in stems:
        path = os.path.join(directory, stem.format(sc=sc) + ext)
        if os.path.exists(path):
            return path
        # The retained campaign stores one directory per model/scenario.
        folder = stem.format(sc=sc)
        if folder.startswith("2B_"):
            folder = "qwen_" + folder
        if folder.endswith("_obs_2"):
            folder = folder[:-2]
        nested = os.path.join(directory, folder, stem.format(sc=sc) + ext)
        if os.path.exists(nested):
            return nested
    return None


def count_log_events(path):
    counts = {k: 0 for k in LOG_PATTERNS}
    if path is None or not os.path.exists(path):
        return counts
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read().lower()
    for k, pat in LOG_PATTERNS.items():
        counts[k] = len(re.findall(pat, text))
    return counts


def aggregate(metric_dicts):
    agg = {
        "total": 0,
        "fallback": 0,
        "invalid_action": 0,
        "backward": 0,
        "certainty_low": 0,
        "refusal": 0,
        "parse_error": 0,
        "missing_field": 0,
        "actions": Counter(),
        "hallucinated": Counter(),
        "ts_issues": Counter(),
        "deltas": [],
    }
    for m in metric_dicts:
        agg["total"] += m["total"]
        agg["fallback"] += m["fallback"]
        agg["invalid_action"] += m["invalid_action"]
        agg["parse_error"] += m["parse_error"]
        agg["missing_field"] += m["missing_field"]
        agg["backward"] += m["backward"]
        agg["certainty_low"] += m["certainty_low"]
        agg["refusal"] += m["refusal"]
        agg["actions"] += m["actions"]
        agg["hallucinated"] += m["hallucinated"]
        agg["ts_issues"] += m["ts_issues"]
        agg["deltas"] += m["deltas"]
    return agg


def row_stats(m):
    """Return the per-run metric tuple used in the results table."""
    total = m["total"]
    valid = sum(m["actions"].values())
    return {
        "calls": total,
        "valid_pct": 100.0 * valid / total if total else 0.0,
        "fallback_pct": 100.0 * m["fallback"] / total if total else 0.0,
        "halluc": sum(m["hallucinated"].values()),
        "backward_pct": 100.0 * m["backward"] / total if total else 0.0,
        "ts_issues": sum(m["ts_issues"].values()),
        "lat_med": median(m["deltas"]),
    }


# ----------------------------------------------------------------------------- Markdown


def md_results_table(rows):
    out = [
        "| Scenario | Model | Calls | Valid % | Fallback % | Hallucinated | "
        "Backward % | TS issues | Lat. med. (s) |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for sc_name, model, s in rows:
        lat = f'{s["lat_med"]:.1f}' if s["lat_med"] is not None else "—"
        out.append(
            f'| {sc_name} | {model} | {s["calls"]} | {s["valid_pct"]:.1f} | '
            f'{s["fallback_pct"]:.1f} | {s["halluc"]} | {s["backward_pct"]:.1f} | '
            f'{s["ts_issues"]} | {lat} |'
        )
    return "\n".join(out)


def md_action_table(a2b, ah):
    order = [
        "FOLLOW_LANE",
        "SLOW_DOWN",
        "STOP",
        "SPEED_UP",
        "TURN_LEFT",
        "TURN_RIGHT",
        "CHANGE_LANE_LEFT",
        "CHANGE_LANE_RIGHT",
    ]
    out = ["| Action | 2B | Haiku |", "|---|--:|--:|"]
    for act in order:
        out.append(f"| {act} | {a2b.get(act, 0)} | {ah.get(act, 0)} |")
    return "\n".join(out)


def md_events_table(events):
    out = [
        "| Scenario | Model | stale | STOP override | commitment | fallback |",
        "|---|---|--:|--:|--:|--:|",
    ]
    for sc_name, model, e in events:
        out.append(
            f'| {sc_name} | {model} | {e["stale"]} | {e["stop_override"]} | '
            f'{e["commitment"]} | {e["fallback"]} |'
        )
    return "\n".join(out)


# -------------------------------------------------------------------------------- LaTeX


def tex_escape(s):
    return s.replace("%", r"\%").replace("_", r"\_")


def tex_results_table(rows):
    out = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Decision quality per scenario and model (qwen3.5:2b vs Claude Haiku 4.5).}",
        r"\label{tab:results-scenario}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{llrrrrrrr}",
        r"\toprule",
        r"Scenario & Model & Calls & Valid \% & Fallback \% & Halluc. & "
        r"Backward \% & TS issues & Lat. med. (s) \\",
        r"\midrule",
    ]
    prev = None
    for sc_name, model, s in rows:
        lat = f'{s["lat_med"]:.1f}' if s["lat_med"] is not None else "--"
        sc_cell = tex_escape(sc_name) if sc_name != prev else ""
        if sc_name != prev and prev is not None:
            out.append(r"\addlinespace")
        out.append(
            f'{sc_cell} & {model} & {s["calls"]} & {s["valid_pct"]:.1f} & '
            f'{s["fallback_pct"]:.1f} & {s["halluc"]} & {s["backward_pct"]:.1f} & '
            f'{s["ts_issues"]} & {lat} \\\\'
        )
        prev = sc_name
    out += [r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}"]
    return "\n".join(out)


def agg_metric_rows(agg2b, aggh):
    """Build the headline aggregate comparison (one row per metric)."""

    def stats(m):
        total = m["total"]
        valid = sum(m["actions"].values())
        return {
            "total": total,
            "valid_pct": 100.0 * valid / total if total else 0.0,
            "fb": m["fallback"],
            "fb_pct": 100.0 * m["fallback"] / total if total else 0.0,
        }

    s2, sh = stats(agg2b), stats(aggh)
    rows = [
        ("Total calls", f'{agg2b["total"]}', f'{aggh["total"]}'),
        ("Valid \\& complete", f'{s2["valid_pct"]:.1f}\\%', f'{sh["valid_pct"]:.1f}\\%'),
        (
            "Fallback rate",
            f'{s2["fb_pct"]:.1f}\\% ({s2["fb"]})',
            f'{sh["fb_pct"]:.1f}\\% ({sh["fb"]})',
        ),
        (
            "\\quad parse / missing / invalid",
            f'{agg2b["parse_error"]} / {agg2b["missing_field"]} / {agg2b["invalid_action"]}',
            f'{aggh["parse_error"]} / {aggh["missing_field"]} / {aggh["invalid_action"]}',
        ),
        (
            "Hallucinated actions (instances)",
            f'{sum(agg2b["hallucinated"].values())}',
            f'{sum(aggh["hallucinated"].values())}',
        ),
        (
            "Backward confusion",
            f'{100.0*agg2b["backward"]/agg2b["total"]:.1f}\\%',
            f'{100.0*aggh["backward"]/aggh["total"]:.1f}\\%',
        ),
        (
            "target\\_speed issues",
            f'{sum(agg2b["ts_issues"].values())}',
            f'{sum(aggh["ts_issues"].values())}',
        ),
        (
            "Low certainty",
            f'{100.0*agg2b["certainty_low"]/agg2b["total"]:.1f}\\%',
            f'{100.0*aggh["certainty_low"]/aggh["total"]:.1f}\\%',
        ),
        ("Latency med / mean (s)", _latency_str(agg2b["deltas"]), _latency_str(aggh["deltas"])),
    ]
    return rows


def _latency_str(deltas):
    if not deltas:
        return "--"
    med = median(deltas)
    mean = sum(deltas) / len(deltas)
    return f"{med:.1f} / {mean:.1f}"


def tex_aggregate_metrics_table(agg2b, aggh):
    out = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Aggregate metric comparison over the five scenarios.}",
        r"\label{tab:aggregate}",
        r"\begin{tabular}{lcc}",
        r"\toprule",
        r"Metric & qwen3.5:2b & Claude Haiku 4.5 \\",
        r"\midrule",
    ]
    for label, v2, vh in agg_metric_rows(agg2b, aggh):
        out.append(f"{label} & {v2} & {vh} \\\\")
    out += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(out)


def md_aggregate_metrics_table(agg2b, aggh):
    out = ["| Metric | qwen3.5:2b | Claude Haiku 4.5 |", "|---|--:|--:|"]
    for label, v2, vh in agg_metric_rows(agg2b, aggh):
        label = label.replace("\\&", "&").replace("\\quad ", "— ").replace("\\_", "_")
        v2 = v2.replace("\\%", "%")
        vh = vh.replace("\\%", "%")
        out.append(f"| {label} | {v2} | {vh} |")
    return "\n".join(out)


def tex_action_table(a2b, ah):
    order = [
        "FOLLOW\\_LANE",
        "SLOW\\_DOWN",
        "STOP",
        "SPEED\\_UP",
        "TURN\\_LEFT",
        "TURN\\_RIGHT",
        "CHANGE\\_LANE\\_LEFT",
        "CHANGE\\_LANE\\_RIGHT",
    ]
    keys = [
        "FOLLOW_LANE",
        "SLOW_DOWN",
        "STOP",
        "SPEED_UP",
        "TURN_LEFT",
        "TURN_RIGHT",
        "CHANGE_LANE_LEFT",
        "CHANGE_LANE_RIGHT",
    ]
    out = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Action distribution (valid calls, aggregated over the five scenarios).}",
        r"\label{tab:actions}",
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Action & 2B & Haiku \\",
        r"\midrule",
    ]
    for disp, key in zip(order, keys):
        out.append(f"{disp} & {a2b.get(key, 0)} & {ah.get(key, 0)} \\\\")
    out += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(out)


def tex_events_table(events):
    out = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Control-layer events per scenario (from the dispatcher logs).}",
        r"\label{tab:control-events}",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Scenario & Model & stale & STOP override & commitment & fallback \\",
        r"\midrule",
    ]
    prev = None
    for sc_name, model, e in events:
        sc_cell = tex_escape(sc_name) if sc_name != prev else ""
        if sc_name != prev and prev is not None:
            out.append(r"\addlinespace")
        out.append(
            f'{sc_cell} & {model} & {e["stale"]} & {e["stop_override"]} & '
            f'{e["commitment"]} & {e["fallback"]} \\\\'
        )
        prev = sc_name
    out += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".", help="directory with the .md/.log files")
    ap.add_argument("--out-dir", default=None, help="where to write outputs (default: --dir)")
    ap.add_argument("--out-prefix", default="tablas_tesis")
    args = ap.parse_args()
    directory = os.path.expanduser(args.dir)
    out_dir = os.path.expanduser(args.out_dir) if args.out_dir else directory

    results_rows, events_rows = [], []
    metrics_2b, metrics_haiku = [], []
    missing = []

    for sc_key, sc_name in SCENARIOS:
        for model, stems in MODEL_STEMS.items():
            md = resolve(directory, stems, sc_key, ".md")
            log = resolve(directory, stems, sc_key, ".log")
            if md is None:
                missing.append(f"{model}/{sc_key} (.md)")
                continue
            m, _ = analyze_file(md)
            (metrics_2b if model == "2B" else metrics_haiku).append(m)
            results_rows.append((sc_name, model, row_stats(m)))
            events_rows.append((sc_name, model, count_log_events(log)))
            if log is None:
                missing.append(f"{model}/{sc_key} (.log)")

    if missing:
        ap.error("Campaign is incomplete: " + ", ".join(missing))
    os.makedirs(out_dir, exist_ok=True)

    # Aggregate rows
    agg_2b = aggregate(metrics_2b)
    agg_h = aggregate(metrics_haiku)
    results_rows.append(("Aggregate", "2B", row_stats(agg_2b)))
    results_rows.append(("Aggregate", "Haiku", row_stats(agg_h)))

    # Assemble documents
    header_note = (
        "> Generated by `make_thesis_tables.py`. The event columns come from "
        "the dispatcher `.log` files; all other columns come from the `.md` files.\n"
    )

    md_doc = [
        "# Comparison tables — Block C\n",
        header_note,
        "## Table 1. Aggregate metric comparison (five scenarios)\n",
        md_aggregate_metrics_table(agg_2b, agg_h),
        "",
        "## Table 2. Decision quality per scenario and model\n",
        md_results_table(results_rows),
        "",
        "## Table 3. Action distribution (aggregate, valid calls)\n",
        md_action_table(agg_2b["actions"], agg_h["actions"]),
        "",
        "## Table 4. Control-layer events per scenario\n",
        md_events_table(events_rows),
        "",
    ]
    tex_doc = [
        "% Block C comparison tables. Requires \\usepackage{booktabs} and \\usepackage{graphicx}.",
        tex_aggregate_metrics_table(agg_2b, agg_h),
        "",
        tex_results_table(results_rows),
        "",
        tex_action_table(agg_2b["actions"], agg_h["actions"]),
        "",
        tex_events_table(events_rows),
        "",
    ]

    md_path = os.path.join(out_dir, args.out_prefix + ".md")
    tex_path = os.path.join(out_dir, args.out_prefix + ".tex")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_doc))
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write("\n".join(tex_doc))

    print(f"Wrote:\n  {md_path}\n  {tex_path}")
    if missing:
        print("\nWARNING - files not found (rows skipped or events zeroed):")
        for x in missing:
            print("  " + x)
    print("\nPreview (Markdown results table):\n")
    print(md_results_table(results_rows))


if __name__ == "__main__":
    main()
