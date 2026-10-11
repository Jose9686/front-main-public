# front-main-public

**Commit scorecard:** is a repository gaining capability, or only moving docs around?

When automated agents commit to a repo all day, the commit count says little.
`commit_scorecard.py` reads `git log` and sorts every commit into two groups:

- **capability:** the commit touches code, meaning `scripts/`, `tests/`,
  `research/`, `ui/`, `deploy/`, or any file with a code extension;
- **doc/state only:** the commit touches only docs, plans or state files.

It also counts commits that touched tests, test lines added, and "jobs only"
commits (one-shot job scripts that are plumbing, reported on their own so they
can't inflate the share).

```
$ python3 scripts/commit_scorecard.py --repo . --since 2026-01-01 --md
| repo | commits | capability | doc/state only | share | commits touching tests | test lines added | jobs only |
|---|---|---|---|---|---|---|---|
| my-repo | 42 | 30 | 12 | 71% | 9 | 310 | 3 |
```

Pass `--repo` more than once to compare repositories. Leave out `--md` for
JSON output. Standard library only.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```
