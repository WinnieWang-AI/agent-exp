"""Tests for stateful Task tool with session_id support."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from kaos.path import KaosPath

from kimi_cli.metadata import WorkDirMeta
from kimi_cli.session import Session
from kimi_cli.session_state import SessionState
from kimi_cli.soul.context import Context
from kimi_cli.tools.multiagent.task import Task
from kimi_cli.wire.file import WireFile


class TestStatefulContextFile:
    """Tests for _get_subagent_context_file with session_id."""

    @pytest.fixture
    def task_with_session(self, runtime):
        """Create a Task tool with a writable session."""
        return Task(runtime)

    @pytest.mark.asyncio
    async def test_session_id_returns_stable_path(self, task_with_session):
        """Same session_id should always return the same file path."""
        path1 = await task_with_session._get_subagent_context_file(session_id="test_session")
        path2 = await task_with_session._get_subagent_context_file(session_id="test_session")
        assert path1 == path2
        assert path1.name == "dialogue_test_session.jsonl"

    @pytest.mark.asyncio
    async def test_different_session_ids_return_different_paths(self, task_with_session):
        """Different session_ids should return different file paths."""
        path1 = await task_with_session._get_subagent_context_file(session_id="session_a")
        path2 = await task_with_session._get_subagent_context_file(session_id="session_b")
        assert path1 != path2
        assert path1.name == "dialogue_session_a.jsonl"
        assert path2.name == "dialogue_session_b.jsonl"

    @pytest.mark.asyncio
    async def test_none_session_id_creates_unique_paths(self, task_with_session):
        """No session_id should create new unique paths each time."""
        path1 = await task_with_session._get_subagent_context_file(session_id=None)
        path2 = await task_with_session._get_subagent_context_file(session_id=None)
        assert path1 != path2

    @pytest.mark.asyncio
    async def test_session_id_path_is_in_session_dir(self, task_with_session, session):
        """Session-based context files should be in the same directory as the main context."""
        path = await task_with_session._get_subagent_context_file(session_id="my_session")
        assert path.parent == session.context_file.parent

    @pytest.mark.asyncio
    async def test_session_id_sanitizes_path_traversal(self, task_with_session):
        """session_id with path separators should be sanitized to prevent traversal."""
        path = await task_with_session._get_subagent_context_file(session_id="../../etc/evil")
        assert "/" not in path.name.replace("dialogue_", "").replace(".jsonl", "")
        assert path.name == "dialogue_______etc_evil.jsonl"

    @pytest.mark.asyncio
    async def test_session_id_sanitizes_special_chars(self, task_with_session):
        """session_id with special characters should be sanitized."""
        path = await task_with_session._get_subagent_context_file(session_id="foo bar!@#$%")
        assert path.name == "dialogue_foo_bar_____.jsonl"

    @pytest.mark.asyncio
    async def test_session_id_empty_string_becomes_unnamed(self, task_with_session):
        """Empty session_id should fall back to 'unnamed'."""
        path = await task_with_session._get_subagent_context_file(session_id="")
        assert path.name == "dialogue_unnamed.jsonl"

    @pytest.mark.asyncio
    async def test_session_id_allows_valid_chars(self, task_with_session):
        """session_id with alphanumeric, hyphens, and underscores should be preserved."""
        path = await task_with_session._get_subagent_context_file(session_id="eval_project-1")
        assert path.name == "dialogue_eval_project-1.jsonl"


class TestContextRestore:
    """Tests verifying that stateful sessions can restore context."""

    @pytest.mark.asyncio
    async def test_context_restore_from_session_file(self, tmp_path):
        """Context should be restorable from a previously written session file."""
        context_file = tmp_path / "dialogue_test.jsonl"

        # Write some history to the file
        from kosong.message import Message

        ctx1 = Context(file_backend=context_file)
        await ctx1.append_message(Message(role="user", content="Hello"))
        await ctx1.append_message(Message(role="assistant", content="Hi there"))
        assert len(ctx1.history) == 2

        # Create a new context and restore
        ctx2 = Context(file_backend=context_file)
        restored = await ctx2.restore()
        assert restored is True
        assert len(ctx2.history) == 2
        assert ctx2.history[0].role == "user"
        assert ctx2.history[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_context_restore_nonexistent_file(self, tmp_path):
        """Restoring from a nonexistent file should return False."""
        context_file = tmp_path / "nonexistent.jsonl"
        ctx = Context(file_backend=context_file)
        restored = await ctx.restore()
        assert restored is False
        assert len(ctx.history) == 0
