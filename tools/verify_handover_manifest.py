"""Verify the tracked handover files against evidence/handover-manifest.json."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "evidence/handover-manifest.json"


def git(*args):
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + ROOT.as_posix(), "-C", str(ROOT), *args]
    )


def verify():
    manifest = json.loads((ROOT / MANIFEST).read_text(encoding="utf-8"))
    entries = manifest["files"]
    paths = [item["path"] for item in entries]
    errors = []
    if len(paths) != len(set(paths)):
        errors.append("Duplicate inventory paths")
    tracked = set(git("ls-files", "-z").decode("utf-8").rstrip("\0").split("\0"))
    expected = tracked - {MANIFEST}
    if set(paths) != expected:
        errors.append("Inventory differs from Git tracked paths: " + repr(sorted(set(paths) ^ expected)))
    for entry in entries:
        relative = Path(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append("Unsafe inventory path: " + entry["path"])
            continue
        file = ROOT / relative
        if not file.is_file():
            errors.append("Missing file: " + entry["path"])
            continue
        data = file.read_bytes()
        if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
            errors.append("Content differs: " + entry["path"])
    if errors:
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(entries)} tracked files match the handover inventory (bytes and SHA-256).")
    print("The manifest excludes itself. This verifies file integrity, not a new test run.")
    return 0


if __name__ == "__main__":
    sys.exit(verify())
