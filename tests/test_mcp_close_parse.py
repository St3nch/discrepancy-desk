"""F-54 — close_run proposed_questions field names must not KeyError."""

from __future__ import annotations

import pytest

from desk.refusals import DeskRefusal
from desk.transports.mcp_tools import parse_proposed_open_question, parse_rendition_unit


def test_proposed_scope_canonical() -> None:
    q = parse_proposed_open_question(
        {
            "text": "Who signed?",
            "rationale": "Signature line is blank.",
            "proposed_scope": "Signature blocks only",
        },
        index=0,
    )
    assert q.proposed_scope == "Signature blocks only"
    assert q.text == "Who signed?"


def test_scope_alias_accepted() -> None:
    """Tool description historically said 'scope'; live executor used it."""
    q = parse_proposed_open_question(
        {
            "text": "Who signed?",
            "rationale": "Signature line is blank.",
            "scope": "Signature blocks only",
        },
        index=0,
    )
    assert q.proposed_scope == "Signature blocks only"


def test_proposed_scope_wins_when_both_present() -> None:
    q = parse_proposed_open_question(
        {
            "text": "Q",
            "rationale": "R",
            "proposed_scope": "canonical",
            "scope": "alias",
        },
        index=0,
    )
    assert q.proposed_scope == "canonical"


def test_missing_proposed_scope_is_structured_refusal_not_keyerror() -> None:
    with pytest.raises(DeskRefusal) as exc:
        parse_proposed_open_question(
            {"text": "Q", "rationale": "R"},
            index=1,
        )
    assert exc.value.code == "OPEN_QUESTION_FIELD_MISSING"
    assert "proposed_scope" in exc.value.what_happened
    assert "proposed_questions[1]" in exc.value.what_happened
    assert "not closed" in exc.value.what_was_preserved.lower()
    assert exc.value.what_you_can_do  # teaches the fix


def test_missing_text_refuses() -> None:
    with pytest.raises(DeskRefusal) as exc:
        parse_proposed_open_question(
            {"rationale": "R", "proposed_scope": "S"},
            index=0,
        )
    assert exc.value.code == "OPEN_QUESTION_FIELD_MISSING"
    assert "text" in exc.value.what_happened


def test_non_object_refuses() -> None:
    with pytest.raises(DeskRefusal) as exc:
        parse_proposed_open_question("not a dict", index=0)
    assert exc.value.code == "OPEN_QUESTION_SHAPE_INVALID"


def test_close_run_tool_description_names_proposed_scope(tmp_path) -> None:
    """Description/schema seam: description must name the keys the parser expects."""
    from sqlalchemy import create_engine

    from desk.transports.mcp_tools import build_mcp_server
    from desk.vault.store import VaultStore

    server = build_mcp_server(create_engine("sqlite://"), vault=VaultStore(tmp_path / "v"))
    tools = {t.name: t for t in server._tool_manager.list_tools()}  # noqa: SLF001
    desc = tools["close_run"].description or ""
    assert "proposed_scope" in desc
    assert "text" in desc
    assert "rationale" in desc


def test_rendition_unit_parse_and_description(tmp_path) -> None:
    """F-58 — same description/schema seam on propose_rendition units."""
    u = parse_rendition_unit({"body": "Hello", "claim_ids": [1, "2"]}, index=0)
    assert u.body == "Hello"
    assert u.claim_ids == [1, 2]

    with pytest.raises(DeskRefusal) as exc:
        parse_rendition_unit({"body": "Hello"}, index=0)
    assert exc.value.code == "RENDITION_UNIT_FIELD_MISSING"

    with pytest.raises(DeskRefusal) as exc2:
        parse_rendition_unit({"body": "Hello", "claim_ids": ["x"]}, index=1)
    assert exc2.value.code == "RENDITION_UNIT_CLAIM_IDS_INVALID"

    from sqlalchemy import create_engine

    from desk.transports.mcp_tools import build_mcp_server
    from desk.vault.store import VaultStore

    server = build_mcp_server(create_engine("sqlite://"), vault=VaultStore(tmp_path / "v"))
    tools = {t.name: t for t in server._tool_manager.list_tools()}  # noqa: SLF001
    desc = tools["propose_rendition"].description or ""
    assert "body" in desc
    assert "claim_ids" in desc
