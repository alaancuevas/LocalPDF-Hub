"""Mutation check for the defenses listed in docs/security-defenses.md.

Removes one defense at a time from a throwaway copy of the repository and
runs the tests, to see whether any test notices. A defense whose removal no
test notices has no test watching it, however green the suite is.

Usage, from the repository root, with the dev requirements installed:

    python security/mutate.py                 # every mutant, both scopes
    python security/mutate.py --only L02,LC   # some mutants
    python security/mutate.py --check         # validate mutants.json only

The copy comes from `git archive HEAD`, so uncommitted changes are not
measured and the working tree is never touched. Results go to
security/results/ (one log per mutant and scope, plus summary.json).
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess  # noqa: S404 -- runs git and pytest with fixed arguments
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SCOPES = {
    "security": ["tests/test_security.py"],
    "full": [],
}
FAILED_LINE = re.compile(r"^(FAILED|ERROR) ")
TIMEOUT_S = 600


def load_mutants(path: Path) -> list[dict]:
    mutants = json.loads(path.read_text(encoding="utf-8"))
    ids = [m["id"] for m in mutants]
    if len(ids) != len(set(ids)):
        sys.exit("mutants.json: duplicate ids")
    if not any(m.get("control") for m in mutants):
        sys.exit("mutants.json: no control mutant, a broken run could not be told apart")
    return mutants


def make_copy() -> Path:
    """A clean copy of HEAD: no local files, caches or databases come along."""
    target = Path(tempfile.mkdtemp(prefix="localpdf-mutate-"))
    archive = subprocess.run(  # noqa: S603
        ["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"],  # noqa: S607
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(target, filter="data")
    return target


def edits_of(mutant: dict) -> list[dict]:
    """A mutant is one replacement, or several under "edits" when a defense spans places."""
    return mutant.get("edits") or [mutant]


def check_finds(copy: Path, mutants: list[dict]) -> None:
    for mutant in mutants:
        for edit in edits_of(mutant):
            text = (copy / edit["file"]).read_text(encoding="utf-8")
            count = text.count(edit["find"])
            if count != 1:
                sys.exit(f"{mutant['id']}: find text occurs {count} times in {edit['file']}")


def apply(copy: Path, mutant: dict) -> dict[Path, str]:
    """Writes the mutant into the copy and returns the originals to restore."""
    originals: dict[Path, str] = {}
    for edit in edits_of(mutant):
        target = copy / edit["file"]
        originals.setdefault(target, target.read_text(encoding="utf-8"))
        text = target.read_text(encoding="utf-8")
        target.write_text(text.replace(edit["find"], edit["replace"], 1), encoding="utf-8")
    return originals


def run_tests(copy: Path, paths: list[str], log: Path) -> str:
    # A stale .pyc of the original module would hide the mutant.
    for cache in copy.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths]
    try:
        done = subprocess.run(  # noqa: S603
            command, cwd=copy, env=env, capture_output=True, text=True, timeout=TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        log.write_text("timeout\n", encoding="utf-8")
        return "timeout"
    output = done.stdout + done.stderr
    log.write_text(output, encoding="utf-8")
    return "survived" if done.returncode == 0 else "killed"


def failing_tests(log: Path) -> list[str]:
    lines = log.read_text(encoding="utf-8").splitlines()
    return sorted({line.split(" - ")[0] for line in lines if FAILED_LINE.match(line)})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mutants", type=Path, default=HERE / "mutants.json")
    parser.add_argument("--out", type=Path, default=HERE / "results")
    parser.add_argument("--only", help="comma-separated mutant ids")
    parser.add_argument("--check", action="store_true", help="validate mutants.json and stop")
    args = parser.parse_args()

    mutants = load_mutants(args.mutants)
    if args.only:
        wanted = set(args.only.split(","))
        mutants = [m for m in mutants if m["id"] in wanted]
    copy = make_copy()
    try:
        check_finds(copy, mutants)
        if args.check:
            print(f"OK: {len(mutants)} mutants, every find text occurs once")
            return 0
        if run_tests(copy, [], copy / "baseline.log") != "survived":
            print("The unmutated suite fails: fix that first.", file=sys.stderr)
            return 2
        args.out.mkdir(parents=True, exist_ok=True)
        results = []
        for mutant in mutants:
            originals = apply(copy, mutant)
            row = {"id": mutant["id"], "defense": mutant["defense"]}
            row["control"] = bool(mutant.get("control"))
            started = time.monotonic()
            try:
                for scope, paths in SCOPES.items():
                    log = args.out / f"{mutant['id']}_{scope}.log"
                    row[scope] = {"status": run_tests(copy, paths, log)}
                    row[scope]["failed"] = failing_tests(log)
            finally:
                for target, original in originals.items():
                    target.write_text(original, encoding="utf-8")
            row["seconds"] = round(time.monotonic() - started, 1)
            results.append(row)
            statuses = " ".join(f"{s}={row[s]['status']}" for s in SCOPES)
            print(f"{mutant['id']:<5} {statuses} | {mutant['defense']}")
    finally:
        shutil.rmtree(copy, ignore_errors=True)

    name = "summary.json" if not args.only else "summary_partial.json"
    (args.out / name).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    counted = [r for r in results if not r["control"] and not r.get("equivalent")]
    for scope in SCOPES:
        killed = [r["id"] for r in counted if r[scope]["status"] == "killed"]
        alive = [r["id"] for r in counted if r[scope]["status"] != "killed"]
        missed = ", ".join(alive) or "-"
        print(f"{scope}: {len(killed)}/{len(counted)} caught; not caught: {missed}")
    control = next((r for r in results if r["control"]), None)
    if control is None:
        return 0
    alive = all(control[s]["status"] == "survived" for s in SCOPES)
    print("control: " + ("survived, the run is valid" if alive else "KILLED, the run is not valid"))
    return 0 if alive else 1


if __name__ == "__main__":
    sys.exit(main())
