# Experiments and results

## Campaign design

The thesis evaluates the same framework with Qwen3.5:2B served by Ollama and Claude Haiku 4.5 through OpenRouter, without task-specific training. All trials used Town10HD and the same spawn point.

| Scenario | Test situation |
| --- | --- |
| Free driving | Navigation without added background traffic |
| Traffic | Background vehicles driving through the urban environment |
| Obstacle | A stationary vehicle ahead of the ego |
| Pedestrian | A crossing triggered by ego proximity |
| Ambulance | An emergency vehicle approaching from behind |

There was one run per model and scenario, with two runs for the obstacle case. Aggregates use the second obstacle run. The exact file selection is recorded in [experiments/runs.json](../experiments/runs.json). The thesis also analyzes the first obstacle run.

A fixed seed helps repeat initialization, but the VLM service, inference timing, occupied spawn points and simulator progression can produce different outcomes. The scenario task requests 15 background vehicles by default; the actual number spawned must be read from each run's log. The CLI added during repository preparation allows scenario selection without editing constants; the experiments have not been repeated with this version.

## Data and metrics

Three sources are distinguished: raw model responses (`.md`), dispatcher messages (`.log`) and recordings for qualitative inspection. Quality metrics mainly describe the model's requested output before control-layer corrections. Committed actions describe what the dispatcher actually accepted.

Historical analysis requires an object with five fields (`scene_analysis`, `risk_assessment`, `action_rationale`, `action`, `certainty`) and an action from the allowed vocabulary. It reports parse errors, missing fields, invalid actions, low certainty and `target_speed` issues. Searching for backward-motion terms provides an approximate textual indicator; it does not establish that the vehicle performed such a maneuver.

The indicator named `Latency` in historical tables is calculated from differences between consecutive response timestamps, with one-second resolution and intervals outside `(0, 120)` seconds discarded. It includes inference, transport and loop cadence; it is not a direct, isolated inference-time measurement.

The extractor recovers JSON more permissively than the historical node: it searches for a brace-delimited object and accepts additional text. The current runtime validator also checks types, finite values and certainty labels. Consequently, the calculated historical fallback rate should not be presented as an exact simulation of the current validator. Actual published events are counted separately in `.log` files.

## Main results

| Metric | Qwen3.5:2B | Claude Haiku 4.5 |
| --- | ---: | ---: |
| Calls | 236 | 278 |
| Valid and complete | 91.5% | 100.0% |
| Calculated fallback rate | 8.5% (20) | 0.0% (0) |
| Actions outside the vocabulary | 11 | 0 |
| `target_speed` issues | 13 | 1 |
| Median / mean interval (s) | 5.0 / 5.5 | 4.0 / 4.5 |

These figures match Table 12 of the [thesis](thesis/TFM_Victor.pdf). The [generated campaign tables](results/tablas_tesis.md) include scenario-level results and controller events. Their action distribution counts valid, complete responses; Table 13 of the thesis uses a different comparison between requested and committed actions, so totals should not be equated without checking the counting criteria.

The evidence points to more consistent outputs from the reference model and a control layer that mitigates errors and delays for both models. The thesis highlights the pedestrian scenario as a boundary: an action can be structurally valid yet semantically inappropriate. In the obstacle scenario, the absence of a destination favors stopping and waiting rather than overtaking. In the ambulance scenario, generic vehicle classification and a front-only camera make rear-approaching emergencies difficult to identify.

The causal contribution of the image was not isolated, and statistical variability was not characterized. These results describe the observed runs; they do not constitute a safety validation or a general comparison between model families.

## Reproduce the analysis

The scripts require only the Python standard library. Complete logs and recordings are retained locally at their historical location and excluded from Git. Regenerating the figures from a public checkout requires supplying those data; summaries and the thesis are included.

```bash
python3 scripts/analysis/parse_runs.py \
  qwen=ros_ws/src/low_control_module/output/qwen_2B_freerun/qwen_2B_freerun.md \
  haiku=ros_ws/src/low_control_module/output/haiku_freerun/haiku_freerun.md

python3 scripts/analysis/make_thesis_tables.py \
  --dir ros_ws/src/low_control_module/output \
  --out-dir /tmp/tfm-tables
```

File resolution supports flat files and the campaign subdirectories. Missing response files or logs cause an explicit error. Compare generated results with `docs/results/tablas_tesis.md` and `.tex` before replacing them. Presentation labels are in English; numerical results and raw records are unchanged.

For new trials, retain the code revision, prompt, sensor configuration, map, spawn point, seed, actual actor count, exact model identifiers and response/log/video files. The experimental prompt remains unchanged during repository preparation.
