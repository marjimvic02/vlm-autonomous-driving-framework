"""Export a source snapshot using .gitignore, without environments or Git history."""

import argparse
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def public_files():
    """Ask an isolated Git index to apply the checkout's ignore rules."""
    with tempfile.TemporaryDirectory(prefix="tfm-export-index-") as temp:
        subprocess.run(["git", "init", "--quiet", temp], check=True)
        result = subprocess.run(
            [
                "git",
                f"--git-dir={temp}/.git",
                f"--work-tree={ROOT}",
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    return [ROOT / name for name in result.stdout.decode().split("\0") if name]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/tfm-source.tar.gz")
    args = parser.parse_args()
    target = args.output.resolve()
    files = [path for path in public_files() if path.resolve() != target]
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        for path in sorted(files):
            archive.add(path, arcname=Path("tfm") / path.relative_to(ROOT), recursive=False)
    print(f"Exported {len(files)} files to {target} ({target.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
