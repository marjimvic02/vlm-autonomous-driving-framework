# Repository preparation for publication

Review date: October 28, 2026.

## Completed plan

1. **Audit:** inventory of modules, dependencies, prompts, scripts, results and documentation; review of the final thesis and comparison of aggregate figures against run records.
2. **Organization:** earlier prototypes in `archive/`, analysis tools in `scripts/analysis/`, result summaries in `docs/results/` and RViz configuration in `config/`.
3. **Portability and cleanup:** removal of active machine-specific paths, completed package metadata, consistent formatting and comments distinguishing context rate, effective decision rate and speed commands.
4. **Presentation:** an executive README, installation and architecture guides, experiment documentation and an unchanged copy of the thesis. Public project documentation, comments and utility messages use English.
5. **Verification:** tests against runtime logic, source/configuration/link checks, regenerated tables and a ROS build in fresh directories.

## Scoped functional changes

- `colcon.meta` is now valid JSON; it previously contained a pasted shell command.
- Pixi tasks use project-relative scripts. CARLA is located through `CARLA_ROOT`. A task pointing to a nonexistent script was corrected.
- The sensor definition is installed with the launch package. Host, port and timeout are propagated to the controller. Experimental delays are preserved and exposed as arguments.
- A failed VLM warmup no longer permanently disables subsequent requests. HTTP failures are detected before parsing response bodies.
- Response validation checks types and certainty labels, discards nonfinite speeds and preserves the `SLOW_DOWN` fallback.
- Invalid messages do not refresh the controller watchdog; an uninitialized controller ignores decisions. Boolean and nonfinite speeds are rejected.
- Scenarios are selected through the CLI; actor positions and trigger rules are preserved. Actors already created are cleaned up if a later setup step fails.
- The table generator resolves the actual campaign subdirectories and reports incomplete campaigns explicitly.

The behavior prompt is preserved byte for byte. Raw records, recordings and the thesis PDF are unchanged. Public table labels have been standardized to English without changing numerical results. These robustness changes postdate the evaluated runs and do not constitute a new validation campaign.

## Verification

- 24 tests without ROS/CARLA cover validation, geometry, actual controller callbacks, the VLM request lifecycle and metric extraction.
- Flake8 and Black cover active project sources; Bash scripts pass syntax checks.
- TOML/JSON/XML configuration parsing and local links in current documentation are checked.
- Markdown and LaTeX tables were regenerated from the retained records; numerical results match the included summaries.
- A clean build completed for **21 ROS packages** in `/tmp`, using the dependencies pinned by `pixi.lock`. Legacy components emitted CMake/setuptools warnings; there were no build errors.
- The installed launch was inspected with `--show-args`, along with the three registered ROS executables; sensor configuration resolves inside the installed package.
- `.env`, `.pixi`, build products, recordings, logs, wheels and dependency Git histories were absent from the public file selection. A limited credential-pattern scan found no matches; it does not replace auditing a Git history that is unavailable here.
- After the language update, source/configuration/link checks and the unit suite were rerun, and the public source archive was regenerated.

CARLA was not started and no real inference request was made during this review. An integrated driving test with an active simulator and provider remains pending. The added CI runs source checks and tests without the simulator; the complete build was verified locally.

To repeat the basic checks with Python 3.11 or later:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/check_source.py
python3 -m pip install -r requirements-dev.txt
python3 -m flake8 scripts tests carla_client_script ros_ws/src/perception_module ros_ws/src/decision_making_module ros_ws/src/low_control_module/low_control_module ros_ws/src/low_control_module/launch ros_ws/src/low_control_module/setup.py
python3 -m black --check --workers 1 scripts tests carla_client_script ros_ws/src/perception_module ros_ws/src/decision_making_module ros_ws/src/low_control_module/low_control_module ros_ws/src/low_control_module/launch ros_ws/src/low_control_module/setup.py
```

Tests import production functions. Callback tests replace ROS/CARLA dependencies with simulated interfaces, rather than duplicating control expressions as the historical script did.

A subsequent [publication privacy review](security-review.md) removed personal mailbox references from package metadata, corrected an archived local path and expanded credential exclusions.

## Local files and publication

Complete historical results (approximately 4.3 GB), environments and build products remain local. `.gitignore` excludes them from public source. New traces are written to `outputs/`. Original dependency Git histories are under `.local/vendor-git/`; the initial project-source backup is under `.local/cleanup/`. Original Spanish development notes are retained under `.local/history/`, with English summaries in the local `archive/` directory, which is also excluded from publication. Vendored dependencies have their revisions, patch and licenses documented in [THIRD_PARTY.md](../THIRD_PARTY.md).

The main `.git` directory available during this review is empty and read-only. A separate local clone under `.local/security/` is used to review the remote history and prepare the publication commit. Publication is authorized with an explicit force-with-lease check against the reviewed remote tip.

To create a portable source snapshot respecting the exclusions:

```bash
python3 scripts/export_source.py
```

The output is `dist/tfm-source.tar.gz`, with a top-level `tfm/` directory. It includes source, vendored dependencies, documentation, the thesis and summary tables. It excludes Git history, complete experimental data, local environments, editor settings and historical prototypes. Extract it into a new directory to initialize a normal Git repository, or copy the files into an existing checkout.

Before publication, an open-source license for the original code may be selected if desired. No such license has been chosen or granted on the author's behalf: metadata reflects reserved rights, while dependencies retain their licenses. An integrated test with the selected CARLA and VLM services is also recommended.
