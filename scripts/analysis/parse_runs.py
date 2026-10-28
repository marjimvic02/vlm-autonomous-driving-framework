#!/usr/bin/env python3
"""
parse_runs.py - metrics extractor for Block E of the VLM driving framework.

Reads one or more debug output_*.md files (one per model run), rebuilds the raw LLM
response of each call and prints the decision-quality metrics side by side so the models
can be compared. It retains the historical campaign criteria. The current runtime validator
also checks field types, certainty labels and finite target speeds.

Only uses the standard library (no pip). Runs on any Python 3.8+.

Usage:
    python3 parse_runs.py 2B=output_2B.md haiku=output_haiku.md
    python3 parse_runs.py output_run1.md output_run2.md          # labels auto-derived
    python3 parse_runs.py --csv per_call.csv 2B=a.md haiku=b.md  # also dump per-call CSV

Notes:
    - The .md stores the RAW model output (before the whitelist/validation), so these
      metrics measure the raw model quality, rather than the quality of committed vehicle actions.
    - Latency is the wall time between calls (gap between consecutive timestamps): it is a
      rough proxy for inference time + loop period, not a pure inference timer.
"""

import sys
import re
import json
import csv
from datetime import datetime
from collections import Counter

# Historical campaign validation criteria; see docs/experiments.md.
VALID_ACTIONS = {
    "FOLLOW_LANE",
    "SPEED_UP",
    "SLOW_DOWN",
    "STOP",
    "TURN_LEFT",
    "TURN_RIGHT",
    "CHANGE_LANE_LEFT",
    "CHANGE_LANE_RIGHT",
}
REQUIRED_FIELDS = ["scene_analysis", "risk_assessment", "action_rationale", "action", "certainty"]
MOTION_ACTIONS = {"FOLLOW_LANE", "SPEED_UP"}  # target_speed == 0 here is a pathology

REFUSAL_PREFIXES = ("i'm sorry", "i am sorry", "i cannot", "i can't", "i can not")
BACKWARD_RE = re.compile(
    r"\b(backward|backwards|reversing|reverse|marcha atr[aá]s)\b", re.IGNORECASE
)

CALL_SPLIT_RE = re.compile(r"^## Call #(\d+)\s*[—-]\s*(.+?)\s*$", re.MULTILINE)
TS_FORMATS = ("%Y-%m-%d %H:%M:%S",)


def parse_timestamp(s):
    s = s.strip()
    for fmt in TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def extract_response_text(block):
    """Return the text after '### LLM Response' within a call block."""
    idx = block.find("### LLM Response")
    if idx == -1:
        return ""
    return block[idx + len("### LLM Response") :].strip()


def extract_json(text):
    """Rough extraction: strip the <think> block and the code fences, then balance the
    first {...} object. Returns (parsed_dict_or_None, raw_cleaned_text)."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"```(?:json)?", "", cleaned).strip()

    start = cleaned.find("{")
    if start == -1:
        return None, cleaned

    depth = 0
    for i in range(start, len(cleaned)):
        c = cleaned[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : i + 1]
                try:
                    return json.loads(candidate), candidate
                except json.JSONDecodeError:
                    return None, candidate
    return None, cleaned


def classify_target_speed(parsed):
    """Return a set of target_speed issue tags for one parsed response."""
    tags = set()
    action = parsed.get("action")
    if "target_speed" not in parsed:
        # Missing is only a pathology for motion actions that need a positive cruise speed
        if action in MOTION_ACTIONS:
            tags.add("ts_missing_on_go")
        return tags
    ts = parsed["target_speed"]
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        if ts is None:
            return tags  # null is the legitimate convention for STOP
        tags.add("ts_non_numeric")
        return tags
    if ts < 0:
        tags.add("ts_negative")
    if ts > 14.0:
        tags.add("ts_out_of_range")
    if ts == 0 and action in MOTION_ACTIONS:
        tags.add("ts_zero_on_go")
    return tags


def analyze_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    matches = list(CALL_SPLIT_RE.finditer(content))
    calls = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        block = content[start:end]
        calls.append(
            {
                "n": int(m.group(1)),
                "ts": parse_timestamp(m.group(2)),
                "block": block,
            }
        )

    m = {
        "file": path,
        "total": len(calls),
        "parse_error": 0,
        "not_dict": 0,
        "missing_field": 0,
        "invalid_action": 0,
        "refusal": 0,
        "fallback": 0,  # would hit publish_fallback in the node
        "certainty_low": 0,  # would be overridden to SLOW_DOWN
        "actions": Counter(),  # raw action distribution (parseable calls)
        "hallucinated": Counter(),
        "ts_issues": Counter(),
        "backward": 0,  # yaw->reverse confusion mentions
        "deltas": [],  # inter-call seconds
    }
    per_call_rows = []

    prev_ts = None
    for c in calls:
        block = c["block"]
        resp = extract_response_text(block)
        parsed, _ = extract_json(resp)

        row = {
            "file": path,
            "call": c["n"],
            "timestamp": c["ts"],
            "action": None,
            "target_speed": None,
            "certainty": None,
            "fallback": False,
            "refusal": False,
            "backward": False,
            "ts_tags": "",
            "note": "",
        }

        # Latency
        if prev_ts and c["ts"]:
            row_delta = (c["ts"] - prev_ts).total_seconds()
            if 0 < row_delta < 120:  # ignore stale-timeout gaps as latency outliers
                m["deltas"].append(row_delta)
        if c["ts"]:
            prev_ts = c["ts"]

        # Refusal (check raw response prefix)
        if resp.strip().lower().startswith(REFUSAL_PREFIXES):
            m["refusal"] += 1
            row["refusal"] = True

        # Backward/reverse confusion (scan whole block text)
        if BACKWARD_RE.search(block):
            m["backward"] += 1
            row["backward"] = True

        if parsed is None:
            m["parse_error"] += 1
            m["fallback"] += 1
            row["fallback"] = True
            row["note"] = "parse_error"
            per_call_rows.append(row)
            continue

        if not isinstance(parsed, dict):
            m["not_dict"] += 1
            m["fallback"] += 1
            row["fallback"] = True
            row["note"] = "not_dict"
            per_call_rows.append(row)
            continue

        action = parsed.get("action")
        row["action"] = action
        row["target_speed"] = parsed.get("target_speed")
        row["certainty"] = parsed.get("certainty")

        missing = [fld for fld in REQUIRED_FIELDS if fld not in parsed]
        if missing:
            m["missing_field"] += 1
            m["fallback"] += 1
            row["fallback"] = True
            row["note"] = "missing:" + ",".join(missing)
            per_call_rows.append(row)
            continue

        if action not in VALID_ACTIONS:
            m["invalid_action"] += 1
            m["hallucinated"][action] += 1
            m["fallback"] += 1
            row["fallback"] = True
            row["note"] = "invalid_action"
            per_call_rows.append(row)
            continue

        # Valid, parseable, complete call
        m["actions"][action] += 1
        if str(parsed.get("certainty", "")).strip().upper() == "LOW":
            m["certainty_low"] += 1

        ts_tags = classify_target_speed(parsed)
        for t in ts_tags:
            m["ts_issues"][t] += 1
        row["ts_tags"] = ",".join(sorted(ts_tags))

        per_call_rows.append(row)

    return m, per_call_rows


def pct(n, d):
    return f"{100.0 * n / d:.1f}%" if d else "—"


def median(xs):
    if not xs:
        return None
    s = sorted(xs)
    k = len(s)
    return s[k // 2] if k % 2 else (s[k // 2 - 1] + s[k // 2]) / 2


def print_report(results):
    labels = [r[0] for r in results]
    mets = [r[1] for r in results]
    w = max(28, *(len(label) for label in labels)) if labels else 28

    def line(name, vals):
        cells = "".join(f"{str(v):>18}" for v in vals)
        print(f"{name:<{w}}{cells}")

    print("\n" + "=" * (w + 18 * len(labels)))
    line("METRIC", labels)
    print("-" * (w + 18 * len(labels)))
    line("Total calls", [m["total"] for m in mets])
    line("Valid & complete", [pct(sum(m["actions"].values()), m["total"]) for m in mets])
    line("Fallback rate", [pct(m["fallback"], m["total"]) for m in mets])
    line("  parse errors", [m["parse_error"] for m in mets])
    line("  missing fields", [m["missing_field"] for m in mets])
    line("  invalid action", [m["invalid_action"] for m in mets])
    line("Refusal rate", [pct(m["refusal"], m["total"]) for m in mets])
    line("Low certainty", [pct(m["certainty_low"], m["total"]) for m in mets])
    line("Backward confusion", [pct(m["backward"], m["total"]) for m in mets])
    line("target_speed issues", [sum(m["ts_issues"].values()) for m in mets])
    line("  non-numeric", [m["ts_issues"].get("ts_non_numeric", 0) for m in mets])
    line("  negative", [m["ts_issues"].get("ts_negative", 0) for m in mets])
    line("  zero on motion", [m["ts_issues"].get("ts_zero_on_go", 0) for m in mets])
    line("  out of range", [m["ts_issues"].get("ts_out_of_range", 0) for m in mets])
    line("  missing on motion", [m["ts_issues"].get("ts_missing_on_go", 0) for m in mets])
    dl = [m["deltas"] for m in mets]
    line("Latency med (s)", [f"{median(d):.1f}" if d else "—" for d in dl])
    line("Latency mean (s)", [f"{sum(d)/len(d):.1f}" if d else "—" for d in dl])
    print("=" * (w + 18 * len(labels)))

    # Detail sections
    for label, m in zip(labels, mets):
        print(f"\n[{label}] action distribution (raw, valid calls):")
        for a, cnt in m["actions"].most_common():
            print(f"    {a:<20} {cnt}")
        if m["hallucinated"]:
            print(f"[{label}] hallucinated actions:")
            for a, cnt in m["hallucinated"].most_common():
                print(f"    {a!r:<20} {cnt}")
    print()


def main(argv):
    args = argv[1:]
    csv_path = None
    if "--csv" in args:
        i = args.index("--csv")
        csv_path = args[i + 1]
        del args[i : i + 2]

    if not args:
        print(__doc__)
        return 1

    results = []
    all_rows = []
    for a in args:
        if "=" in a:
            label, path = a.split("=", 1)
        else:
            label, path = a.rsplit("/", 1)[-1].replace(".md", ""), a
        m, rows = analyze_file(path)
        results.append((label, m))
        for r in rows:
            r["label"] = label
        all_rows.extend(rows)

    print_report(results)

    if csv_path:
        cols = [
            "label",
            "file",
            "call",
            "timestamp",
            "action",
            "target_speed",
            "certainty",
            "fallback",
            "refusal",
            "backward",
            "ts_tags",
            "note",
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            wtr = csv.DictWriter(f, fieldnames=cols)
            wtr.writeheader()
            for r in all_rows:
                wtr.writerow({k: r.get(k, "") for k in cols})
        print(f"Per-call CSV written to {csv_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
