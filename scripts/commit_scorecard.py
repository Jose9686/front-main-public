#!/usr/bin/env python3
"""commit_scorecard.py — is a repo gaining capability, or only moving docs around? Measured from git.

A "capability" commit touches code: scripts/, tests/, research/, ui/, deploy/, or any file with a code
extension. The rest only edit docs, plans or state. The share of capability commits over a window is a
cheap, honest signal of whether work is shipping, especially when automated agents commit often.

    python3 scripts/commit_scorecard.py --repo . --since 2026-01-01
    python3 scripts/commit_scorecard.py --repo ../a --repo ../b --since 2026-01-01 --md

Standard library only; merge commits are skipped (their branch commits are counted on their own).
"""
import argparse, datetime, json, os, subprocess, sys

# Directories whose files count as capability.
CAPABILITY_DIRS = ("scripts/", "tests/", "research/", "ui/", "deploy/")
# Anywhere else, code by extension still counts; a .md or a json state file does not.
CODE_EXT = (".py", ".sh", ".js", ".html", ".css", ".service", ".timer", ".toml", ".yml", ".yaml")
# Files that are never capability even inside a capability directory (a plan or a rebuilt dashboard).
NEVER_DIRS = ("plans/", "state/", "cache/", "docs/")
TEST_MARKERS = ("tests/", "test_")


def is_capability_path(path):
    p = path.replace("\\", "/")
    if p.startswith(NEVER_DIRS) or any(("/" + d) in p for d in NEVER_DIRS):
        return False
    if p.startswith("research/"):
        return True  # research write-ups count, even as .md
    if p.startswith(CAPABILITY_DIRS):
        return not p.endswith((".md", ".txt"))  # ui/README.md or ui/IMPROVEMENTS.md alone is a doc commit
    return p.endswith(CODE_EXT)


def is_job_path(path):
    """A one-shot job file for a machine's inbox (deploy/<box>/jobs/<name>.sh): code by the rule above, but a
    commit made only of these is plumbing, not capability. Reported in its own column so it can't inflate the share."""
    p = path.replace("\\", "/")
    parts = p.split("/")
    return len(parts) == 4 and parts[0] == "deploy" and parts[2] == "jobs" and parts[3].endswith(".sh")


def is_test_path(path):
    p = path.replace("\\", "/")
    return p.startswith("tests/") or os.path.basename(p).startswith("test_") or p.endswith("_test.py")


def classify(commits):
    """commits: list of {"sha","date","subject","files":[(path, added, deleted)]}. Returns the tallies."""
    total = capability = tests_touched = jobs_only = 0
    test_lines_added = files_changed = 0
    for c in commits:
        total += 1
        files = c["files"]
        files_changed += len(files)
        if any(is_capability_path(p) for p, _, _ in files):
            capability += 1
        if files and all(is_job_path(p) for p, _, _ in files):
            jobs_only += 1   # counted inside `capability` too: the old columns do not move
        touched = [(p, a) for p, a, _ in files if is_test_path(p)]
        if touched:
            tests_touched += 1
            test_lines_added += sum(a for _, a in touched)
    share = (capability / total) if total else None
    return {"commits": total, "capability": capability, "doc_or_state_only": total - capability,
            "capability_share": share, "commits_touching_tests": tests_touched,
            "test_lines_added": test_lines_added, "files_changed": files_changed, "jobs_only": jobs_only}


def parse_numstat(text):
    """`git log --format=%H|%aI|%s --numstat` output -> the commit list classify() reads."""
    commits, cur = [], None
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) == 3 and len(parts[0]) == 40 and all(ch in "0123456789abcdef" for ch in parts[0]):
            cur = {"sha": parts[0], "date": parts[1], "subject": parts[2], "files": []}
            commits.append(cur)
            continue
        if cur is None:
            continue
        cols = line.split("\t")
        if len(cols) == 3:
            added = int(cols[0]) if cols[0].isdigit() else 0  # "-" for binary files
            deleted = int(cols[1]) if cols[1].isdigit() else 0
            cur["files"].append((cols[2], added, deleted))
    return commits


def git_commits(repo, since, until=None, branch=None):
    cmd = ["git", "-C", repo, "log", "--no-merges", "--format=%H|%aI|%s", "--numstat", f"--since={since}"]
    if until:
        cmd.append(f"--until={until}")
    if branch:
        cmd.append(branch)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if p.returncode:
        raise RuntimeError(f"git log failed in {repo}: {p.stderr.strip()[:300]}")
    return parse_numstat(p.stdout)


def pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def render_md(results, since, until):
    span = f"since {since}" + (f" until {until}" if until else "")
    out = [f"**Capability share** ({span}; capability = a commit touching scripts/, tests/, research/, ui/, deploy/ or code; the rest only moved docs, plans or state):", "",
           "| repo | commits | capability | doc/state only | share | commits touching tests | test lines added | jobs only |",
           "|---|---|---|---|---|---|---|---|"]
    for name, r in results:
        out.append(f"| {name} | {r['commits']} | {r['capability']} | {r['doc_or_state_only']} | {pct(r['capability_share'])} | {r['commits_touching_tests']} | {r['test_lines_added']} | {r.get('jobs_only', 0)} |")
    if any(r.get("jobs_only") for _, r in results):
        out.append("")
        out.append("`jobs only` = commits made only of `deploy/<box>/jobs/*.sh` files (one-shot plumbing); they sit inside `capability`, so capability minus jobs only is the honest share.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", action="append", default=[], help="git clone to measure (repeatable; default .)")
    ap.add_argument("--since", default=None, help="git --since (default: yesterday)")
    ap.add_argument("--until", default=None)
    ap.add_argument("--branch", default=None, help="measure this ref instead of HEAD (e.g. origin/main)")
    ap.add_argument("--md", action="store_true", help="markdown instead of JSON")
    a = ap.parse_args(argv)
    repos = a.repo or ["."]
    since = a.since or (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    results = []
    for repo in repos:
        name = os.path.basename(os.path.abspath(repo)) or repo
        try:
            results.append((name, classify(git_commits(repo, since, a.until, a.branch))))
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            print(f"{name}: {e}", file=sys.stderr)
            return 2
    if a.md:
        print(render_md(results, since, a.until))
    else:
        print(json.dumps({"since": since, "until": a.until, "repos": dict(results)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
