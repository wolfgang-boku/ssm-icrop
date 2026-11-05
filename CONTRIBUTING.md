# Contributing

This project follows [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow)
and the conventional 50/72 commit message format. The rules below are short on
purpose; the hooks in `.githooks/` and the CI enforce the mechanical ones.

## Setup

Create the environment with [uv](https://docs.astral.sh/uv/) and enable the
repository's git hooks once per clone:

```bash
uv sync --extra dev
git config core.hooksPath .githooks
```

## Dependencies

`uv.lock` pins every package version; CI installs exactly these and fails if
the lockfile no longer matches `pyproject.toml`.

- After changing dependencies in `pyproject.toml`, run `uv lock` and commit
  `uv.lock` together with it.
- Upgrade deliberately, on a `chore/` branch of its own: `uv lock --upgrade`,
  then `uv sync --extra dev` and the full test suite. The pull request's CI
  run shows whether the new versions break anything.

## Language

Everything tracked in this repository is written in English: code, comments,
docstrings, documentation, config comments, commit messages, pull request
titles and descriptions.

## Branches

- `main` always passes CI. Nothing is committed to it directly (the
  `pre-commit` hook refuses); changes reach it only through a pull request
  whose CI run is green.
- One branch per topic, created from an up-to-date `main` and named
  `<type>/<short-description>` in lowercase kebab-case:

  | Type | For |
  |---|---|
  | `feature/` | new model sections and features |
  | `fix/` | porting errors and other bugs |
  | `docs/` | documentation only |
  | `refactor/` | restructuring without behaviour change |
  | `test/` | tests and verification only |
  | `chore/` | tooling, CI, dependencies, repository housekeeping |

- A branch's name describes everything on it. When the next change belongs to
  a different topic, start a new branch from `main` instead of adding to the
  current one.
- Keep branches short-lived: open the pull request as soon as the topic is
  complete and CI is green, merge it, then delete the branch locally and on
  GitHub.

## Commits

One logical change per commit. Lint and tests pass before committing:

```bash
ruff check src/ tests/ scripts/
pytest
```

Changes under `src/ssm_icrop/` must keep the VBA fidelity rules in
[CLAUDE.md](CLAUDE.md#fidelity-rules).

### Commit messages

```
Read crop parameters from the workbook          <- subject

The Crop sheet stores one cultivar per column. Reading it directly    <- body
removes the hand-transcription step, which had already rounded IRUE
from 2.4200000000000004 to 2.42.
```

- **Subject:** imperative mood ("Add", "Fix", "Port" — not "Added" or
  "Adds"), capitalised, no trailing period. Aim for 50 characters; 72 is the
  hard limit.
- A blank line separates subject and body.
- **Body:** explains what changed and why, not how — the diff shows how.
  Wrap at 72 characters. Omit it only for changes that explain themselves.
- Cite VBA source as `iCrop.vba:<line>`.

The `commit-msg` hook checks the subject length, capitalisation, trailing
period, blank line and body wrapping; CI runs the same check on every commit
of a pull request.
