"""Tests for scripts/check_commit_msg.py, the commit message format check."""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "check_commit_msg", REPO_ROOT / "scripts" / "check_commit_msg.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_commit_msg"] = module
    spec.loader.exec_module(module)
    return module


check_message = _load_checker().check_message


def test_well_formed_message_passes():
    message = (
        "Read crop parameters from the workbook\n"
        "\n"
        "The Crop sheet stores one cultivar per column. Reading it directly\n"
        "removes the hand-transcription step.\n"
        "\n"
        "Co-Authored-By: Someone <someone@example.com>\n"
    )
    assert check_message(message) == []


def test_subject_only_passes():
    assert check_message("Fix the runoff curve number lookup\n") == []


def test_subject_rules():
    errors = check_message("added a thing.\n")
    assert "subject must start with a capital letter" in errors
    assert "subject must not end with a period" in errors
    assert check_message("A" * 72) == []
    assert check_message("A" * 73) == ["subject is 73 characters; the limit is 72"]


def test_empty_message_fails():
    assert check_message("\n# only a git comment\n") == ["subject is empty"]


def test_missing_blank_line_fails():
    assert check_message("Fix it\nbody starts here\n") == [
        "line 2 must be blank (it separates subject and body)"
    ]


def test_body_counts_characters_not_bytes():
    # 72 characters, but more than 72 bytes in UTF-8.
    prefix = "CO₂ effect — "
    line = prefix + "x" * (72 - len(prefix))
    assert len(line) == 72 and len(line.encode()) > 72
    assert check_message(f"Fix it\n\n{line}\n") == []


def test_long_body_line_fails_unless_unbreakable():
    long_line = "word " * 15
    assert check_message(f"Fix it\n\n{long_line}\n") == [
        f"body line 3 is {len(long_line)} characters; wrap at 72"
    ]
    url = "See https://example.com/" + "a" * 80
    assert check_message(f"Fix it\n\n{url}\n") == []
    assert check_message(f"Fix it\n\n{'a' * 90}\n") == []


def test_git_generated_messages_are_exempt():
    assert check_message("Merge branch 'feature/x' into main\n") == []
    assert check_message('Revert "Add something"\n') == []
