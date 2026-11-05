"""Check commit messages against the 50/72 format described in CONTRIBUTING.md.

Only the mechanical rules are checked here: subject length, capitalisation and
trailing period, the blank line after the subject, and body wrapping. Whether
the message is clear, in English and in the imperative mood is left to review.

Usage:
    python3 scripts/check_commit_msg.py <message-file>    # as the commit-msg hook
    python3 scripts/check_commit_msg.py --range A..B      # every commit in a range (CI)

Standard library only, so the hook runs without the project environment.
"""

import argparse
import re
import subprocess
import sys

SUBJECT_LIMIT = 72
BODY_LIMIT = 72

# Messages git generates itself are not held to the format.
EXEMPT_SUBJECT = re.compile(r"^(Merge|Revert|fixup!|squash!|amend!) ")


def check_message(message: str) -> list[str]:
    """Return the rule violations in a commit message; empty if it passes."""
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines or not lines[0].strip():
        return ["subject is empty"]

    subject = lines[0]
    if EXEMPT_SUBJECT.match(subject):
        return []

    errors = []
    if len(subject) > SUBJECT_LIMIT:
        errors.append(f"subject is {len(subject)} characters; the limit is {SUBJECT_LIMIT}")
    if not subject[0].isupper():
        errors.append("subject must start with a capital letter")
    if subject.endswith("."):
        errors.append("subject must not end with a period")
    if len(lines) > 1 and lines[1].strip():
        errors.append("line 2 must be blank (it separates subject and body)")
    for number, line in enumerate(lines[2:], start=3):
        # A URL or a single unbreakable token may exceed the limit.
        if len(line) > BODY_LIMIT and "://" not in line and " " in line.strip():
            errors.append(f"body line {number} is {len(line)} characters; wrap at {BODY_LIMIT}")
    return errors


def _messages_in_range(rev_range: str) -> list[tuple[str, str]]:
    shas = subprocess.run(
        ["git", "rev-list", "--no-merges", rev_range],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return [
        (sha[:7], subprocess.run(
            ["git", "log", "-1", "--format=%B", sha],
            capture_output=True, text=True, check=True,
        ).stdout)
        for sha in shas
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("message_file", nargs="?", help="file holding one commit message")
    source.add_argument("--range", help="git revision range, e.g. origin/main..HEAD")
    args = parser.parse_args()

    if args.range:
        messages = _messages_in_range(args.range)
    else:
        with open(args.message_file, encoding="utf-8") as f:
            messages = [("message", f.read())]

    failed = False
    for label, message in messages:
        for error in check_message(message):
            print(f"commit-msg: {label}: {error}", file=sys.stderr)
            failed = True
    if failed:
        print('See CONTRIBUTING.md, "Commit messages".', file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
