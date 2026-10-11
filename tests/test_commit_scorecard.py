"""Tests for scripts/commit_scorecard.py (temporary git repos, no network).

    python3 -m unittest discover -s tests -t .      or      python3 tests/test_commit_scorecard.py
"""
import os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
SCRIPT = os.path.join(ROOT, "scripts", "commit_scorecard.py")
import commit_scorecard as imp  # noqa: E402


def git(repo, *args, env=None):
    e = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x",
             GIT_AUTHOR_DATE="2026-09-24T06:00:00+00:00", GIT_COMMITTER_DATE="2026-09-24T06:00:00+00:00")
    subprocess.run(["git", "-C", repo] + list(args), check=True, capture_output=True, env=e)


def commit_file(repo, path, text, msg):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "a") as f:
        f.write(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)


def make_fixture_repo(d):
    """Six commits: three capability (scripts, tests+scripts, ui), three doc/state (README, state, plans)."""
    git(d, "init", "-q", "-b", "main")
    commit_file(d, "scripts/a.py", "print(1)\n", "1 script")
    commit_file(d, "README.md", "# hi\n", "2 readme")
    commit_file(d, "state/book.json", "{}\n", "3 state")
    commit_file(d, "tests/test_a.py", "def test_a():\n    assert 1\n", "4 test")
    commit_file(d, "plans/x/PLAN.md", "plan\n", "5 plan")
    commit_file(d, "ui/index.html", "<p>x</p>\n", "6 ui")


def test_paths():
    assert imp.is_capability_path("scripts/x.py")
    assert imp.is_capability_path("ui/index.html")
    assert imp.is_capability_path("deploy/server/heartbeat.sh")
    assert imp.is_capability_path("research/plan.md")  # research/ counts
    assert imp.is_capability_path("setup.sh")  # code by extension outside the dirs
    assert not imp.is_capability_path("README.md")
    assert not imp.is_capability_path("ui/IMPROVEMENTS.md") and not imp.is_capability_path("ui/README.md")
    assert not imp.is_capability_path("deploy/server/README.md")
    assert not imp.is_capability_path("plans/x/PLAN.md")
    assert not imp.is_capability_path("state/x.json")
    assert not imp.is_capability_path("ui/plans/x.py")  # a plans/ segment anywhere never counts
    assert imp.is_test_path("tests/test_a.py") and imp.is_test_path("ui/test_ui.py") and not imp.is_test_path("scripts/a.py")


def test_parse_numstat_and_classify():
    text = ("a" * 40 + "|2026-09-24T06:00:00+00:00|one\n\n3\t0\tscripts/a.py\n-\t-\timg.png\n"
            + "b" * 40 + "|2026-09-24T06:01:00+00:00|two|with|pipes\n\n1\t1\tREADME.md\n")
    commits = imp.parse_numstat(text)
    assert len(commits) == 2 and commits[1]["subject"] == "two|with|pipes"
    assert commits[0]["files"] == [("scripts/a.py", 3, 0), ("img.png", 0, 0)]
    r = imp.classify(commits)
    assert r["commits"] == 2 and r["capability"] == 1 and r["capability_share"] == 0.5
    assert imp.classify([])["capability_share"] is None


def test_fixture_repo():
    if not shutil.which("git"):
        print("skip: no git")
        return
    d = tempfile.mkdtemp(prefix="scorecard-")
    try:
        make_fixture_repo(d)
        r = imp.classify(imp.git_commits(d, "2026-09-23"))
        assert r["commits"] == 6, r
        assert r["capability"] == 3 and r["doc_or_state_only"] == 3, r
        assert r["capability_share"] == 0.5, r
        assert r["commits_touching_tests"] == 1 and r["test_lines_added"] == 2, r
        # nothing after the fixture's date
        assert imp.classify(imp.git_commits(d, "2026-09-25"))["commits"] == 0
        # the CLI, markdown and JSON
        p = subprocess.run([sys.executable, SCRIPT, "--repo", d, "--since", "2026-09-23", "--md"],
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        assert "| 6 | 3 | 3 | 50% | 1 | 2 |" in p.stdout, p.stdout
        p = subprocess.run([sys.executable, SCRIPT, "--repo", os.path.join(d, "nope"), "--since", "2026-09-23"],
                           capture_output=True, text=True)
        assert p.returncode == 2 and "git log failed" in p.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_jobs_column():
    """A commit made only of deploy/<box>/jobs/*.sh files is counted in `jobs only`; the old columns do not move."""
    assert imp.is_job_path("deploy/server/jobs/20260924-0823-x.sh") and imp.is_job_path("deploy/laptop/jobs/a.sh")
    assert not imp.is_job_path("deploy/server/jobs.sh") and not imp.is_job_path("deploy/server/heartbeat.sh")
    assert not imp.is_job_path("deploy/server/jobs/README.md") and not imp.is_job_path("scripts/jobs/a.sh")
    text = ("a" * 40 + "|2026-09-24T06:00:00+00:00|job\n\n3\t0\tdeploy/server/jobs/0001-x.sh\n"
            + "b" * 40 + "|2026-09-24T06:01:00+00:00|script\n\n1\t0\tscripts/a.py\n"
            + "c" * 40 + "|2026-09-24T06:02:00+00:00|job+script\n\n1\t0\tdeploy/server/jobs/0002-y.sh\n1\t0\tscripts/b.py\n")
    r = imp.classify(imp.parse_numstat(text))
    assert r["commits"] == 3 and r["capability"] == 3 and r["jobs_only"] == 1, r
    if not shutil.which("git"):
        print("skip: no git")
        return
    d = tempfile.mkdtemp(prefix="scorecard-jobs-")
    try:
        git(d, "init", "-q", "-b", "main")
        commit_file(d, "deploy/server/jobs/0001-x.sh", "echo hi\n", "1 job")
        commit_file(d, "scripts/a.py", "print(1)\n", "2 script")
        p = subprocess.run([sys.executable, SCRIPT, "--repo", d, "--since", "2026-09-23", "--md"],
                           capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        assert "| 2 | 2 | 0 | 100% | 0 | 0 | 1 |" in p.stdout, p.stdout
        assert "jobs only" in p.stdout
    finally:
        shutil.rmtree(d, ignore_errors=True)


class ScorecardTests(unittest.TestCase):
    def test_paths(self): test_paths()
    def test_parse_numstat_and_classify(self): test_parse_numstat_and_classify()
    def test_fixture_repo(self): test_fixture_repo()
    def test_jobs_column(self): test_jobs_column()


if __name__ == "__main__":
    unittest.main()
