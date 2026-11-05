---
name: commit
description: Make a git commit in this repository following CONTRIBUTING.md — check that the change belongs on the current branch (or start a new one), keep one logical change per commit, run lint and tests, write an English 50/72 message, and say when the branch is ready for a pull request. Use for every commit, whether the user types /commit or asks to commit in words.
---

# Committing

The mechanical rules (no commits on `main`, message format) are enforced by
`.githooks/`. This skill covers the judgement calls the hooks cannot make.
Never push and never open a pull request unless the user explicitly asks for
it in the current message.

## 1. Look before deciding

```bash
git config core.hooksPath     # must print .githooks; if not, set it and say so
git status --short
git diff HEAD --stat
git branch --show-current
git log --oneline main..HEAD
```

Read the full diff of what is about to be committed.

## 2. Does the change belong on this branch?

The branch name states its topic (`<type>/<description>`, types in
CONTRIBUTING.md). Compare it with the diff:

- **On `main`:** create a topic branch from `main` and commit there.
- **Same topic:** commit here.
- **Different topic:** do not add it to this branch. If the current branch's
  work is complete, it should be merged first (step 6). Otherwise move the
  change to a new branch from `main` (`git stash`, `git switch main`,
  `git switch -c <type>/<description>`, `git stash pop`). When the change
  depends on unmerged work on the current branch, say so and ask.
- **Topic drifted:** if the branch name no longer describes what is on it,
  say so instead of silently continuing.

When the right branch is unclear, ask the user rather than guess.

## 3. One logical change per commit

If the diff mixes independent changes (a fix and an unrelated doc edit, a
refactor and a behaviour change), split them into separate commits by
staging paths explicitly with `git add <paths>`. Never `git add -A` without
having read what it stages. Unrelated changes in the same file: ask.

## 4. Checks

```bash
ruff check src/ tests/ scripts/
pytest
```

Do not commit failing lint or tests without telling the user and getting an
explicit go-ahead. If the diff touches `src/ssm_icrop/`, offer to run the
`vba-fidelity-auditor` agent before committing.

The repository is public: check the diff and the message for content that
belongs in `CLAUDE.local.md` instead (see "Public repository" in CLAUDE.md).

## 5. The message

Follow "Commit messages" in CONTRIBUTING.md:

- English, imperative subject ("Port SoilWater runoff", not "Ported …"),
  capitalised, no period, aim for 50 characters, never over 72.
- Blank line, then a body wrapped at 72 that says **what changed and why**.
  The reader has the diff; the body carries what the diff cannot show — the
  reason, the VBA citation (`iCrop.vba:<line>`), what was verified, what was
  deliberately left out.
- No file lists, no "this commit …", no vague subjects ("Update files",
  "Fixes", "WIP").
- Too short: a subject that needs a body and has none. Too long: a body that
  narrates the work session instead of explaining the change.

Commit with the message passed through a heredoc, and end it with the
attribution trailer from the session instructions.

## 6. After the commit: is the branch done?

Look at `git log --oneline main..HEAD` and judge whether the branch's topic is
complete: the feature works, tests are green, docs touched by it are updated.

- **Complete:** tell the user the branch is ready for a pull request and
  merge into `main`, and offer to push it and open the PR. Pushing needs
  their explicit instruction.
- **Not complete:** say in one line what is still missing.
- **Long-lived:** if the branch carries more than one topic or has gone
  several sessions without a merge, raise it before adding more to it.
