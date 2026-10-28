"""Check source syntax, configuration and documentation without ROS or CARLA."""

import ast
import json
import re
import sys
import tomllib
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ["perception_module", "decision_making_module", "low_control_module"]


def main():
    errors = []
    roots = [ROOT / "scripts", ROOT / "tests", ROOT / "carla_client_script"]
    roots.extend(ROOT / "ros_ws/src" / package for package in PACKAGES)
    sources = [
        path
        for directory in roots
        for path in directory.rglob("*.py")
        if "output" not in path.relative_to(ROOT).parts
    ]
    for path in sources:
        try:
            text = path.read_text(encoding="utf-8")
            ast.parse(text, filename=str(path))
            if re.search(r"\x2fhome/[^/]+/(?:tfm|carla)[/\w.-]*", text):
                errors.append(f"{path.relative_to(ROOT)}: machine-specific runtime path")
        except (SyntaxError, UnicodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    for name in ["pixi.toml", "pyproject.toml"]:
        with (ROOT / name).open("rb") as stream:
            tomllib.load(stream)
    for name in [
        "ros_ws/colcon.meta",
        "experiments/runs.json",
        "ros_ws/src/low_control_module/launch/objects.json",
    ]:
        json.loads((ROOT / name).read_text())
    for package in PACKAGES:
        tree = ElementTree.parse(ROOT / "ros_ws/src" / package / "package.xml")
        if tree.findtext("name") != package:
            errors.append(f"{package}: package name mismatch")
        if "TODO" in ElementTree.tostring(tree.getroot(), encoding="unicode"):
            errors.append(f"{package}: placeholder package metadata")
    documents = list((ROOT / "docs").rglob("*.md"))
    documents.extend(ROOT / name for name in ["README.md", "THIRD_PARTY.md"])
    for path in documents:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text()):
            if target.startswith(("https:", "http:", "#", "mailto:")):
                continue
            target = target.split("#")[0]
            if not (path.parent / target).exists():
                errors.append(f"{path.relative_to(ROOT)}: broken link {target}")
    for error in errors:
        print(error, file=sys.stderr)
    print(f"Checked {len(sources)} Python files, configuration and {len(documents)} documents.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
