"""Tests for video agent specifications."""

from __future__ import annotations

from kimi_cli.agentspec import (
    VIDEO_CREATOR_AGENT_FILE,
    VIDEO_DIRECTOR_AGENT_FILE,
    VIDEO_EVALUATOR_AGENT_FILE,
    load_agent_spec,
)


def test_load_video_creator_spec():
    """Test loading the video-creator agent specification."""
    spec = load_agent_spec(VIDEO_CREATOR_AGENT_FILE)
    assert spec.name == "video-creator"
    assert "kimi_cli.tools.video:GenerateVideo" in spec.tools
    assert "kimi_cli.tools.video:CheckVideoJob" in spec.tools
    assert "kimi_cli.tools.video:VideoEdit" in spec.tools
    assert "kimi_cli.tools.video:ManageVideoProject" in spec.tools
    assert "kimi_cli.tools.video:GenerateImage" in spec.tools
    # Should also have base tools
    assert "kimi_cli.tools.file:ReadFile" in spec.tools
    assert "kimi_cli.tools.shell:Shell" in spec.tools
    # Should have coder subagent
    assert "coder" in spec.subagents


def test_load_video_evaluator_spec():
    """Test loading the video-evaluator agent specification."""
    spec = load_agent_spec(VIDEO_EVALUATOR_AGENT_FILE)
    assert spec.name == "video-evaluator"
    assert "kimi_cli.tools.file:ReadFile" in spec.tools
    assert "kimi_cli.tools.file:ReadMediaFile" in spec.tools
    # Should NOT have video generation tools
    assert "kimi_cli.tools.video:GenerateVideo" not in spec.tools
    # Should NOT have subagents
    assert len(spec.subagents) == 0


def test_load_video_director_spec():
    """Test loading the video-director agent specification."""
    spec = load_agent_spec(VIDEO_DIRECTOR_AGENT_FILE)
    assert spec.name == "video-director"
    assert "kimi_cli.tools.multiagent:Task" in spec.tools
    # Should have both subagents
    assert "video-creator" in spec.subagents
    assert "video-evaluator" in spec.subagents
    # Director should NOT have video tools directly
    assert "kimi_cli.tools.video:GenerateVideo" not in spec.tools
