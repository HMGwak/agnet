from pathlib import Path
from types import SimpleNamespace
import json

import pytest
from pytest_httpx import HTTPXMock

from app.adapters.codex_runner import CodexRunner
from app.bootstrap.codex_sidecar import CodexSidecarManager
from app.core.codex_project_config import CodexProjectConfig
from app.core.project_policy import ProjectPolicy
from app.core.prompt_library import PromptLibrary


def make_policy():
    return ProjectPolicy(
        plan_required=True,
        critique_required=True,
        critique_max_rounds=2,
        test_fix_loops=2,
        review_required=True,
        merge_human_approval=True,
        allow_user_override=False,
        allow_repo_override=False,
        main_allow_feature_work=False,
        main_allow_hotfix=True,
        main_allow_plan_review=True,
        auto_fork_feature_workspace_from_main=True,
        hotfix_keywords=("fix", "bug"),
        plan_review_keywords=("plan", "review"),
    )


def make_prompts():
    return PromptLibrary(
        templates={
            "plan": SimpleNamespace(substitute=lambda context: f"PLAN::{context['task_input']}"),
            "critique": SimpleNamespace(
                substitute=lambda context: f"CRITIQUE::{context['plan_text']}::{context['task_input']}"
            ),
            "implement": SimpleNamespace(
                substitute=lambda context: f"IMPLEMENT::{context['plan_text']}::{context['task_input']}"
            ),
            "test": SimpleNamespace(
                substitute=lambda context: f"TEST::{context['plan_text']}::{context['task_input']}"
            ),
            "review": SimpleNamespace(
                substitute=lambda context: f"REVIEW::{context['plan_text']}::{context['task_input']}"
            ),
        }
    )


def make_project_config(tmp_path: Path) -> CodexProjectConfig:
    project_dir = tmp_path / ".codex"
    agent_dir = project_dir / "agents"
    instructions_dir = project_dir / "instructions"
    agent_dir.mkdir(parents=True)
    instructions_dir.mkdir()

    agent_files = {}
    base_config = {
        "model": "gpt-5.4",
        "approval_policy": "never",
        "sandbox_mode": "workspace-write",
        "features": {"multi_agent": False},
        "agents": {},
    }
    for name, multi_agent in (
        ("intake", False),
        ("planner", False),
        ("critic", False),
        ("executor", True),
        ("tester", False),
        ("reviewer", False),
    ):
        instruction_file = instructions_dir / f"{name}.md"
        instruction_file.write_text(f"{name} instructions", encoding="utf-8")
        agent_file = agent_dir / f"{name}.toml"
        agent_file.write_text(
            "\n".join(
                [
                    'model = "gpt-5.4"',
                    'approval_policy = "never"',
                    'sandbox_mode = "workspace-write"',
                    f'model_instructions_file = "../instructions/{name}.md"',
                    "",
                    "[features]",
                    f"multi_agent = {'true' if multi_agent else 'false'}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        agent_files[name] = agent_file.resolve()
        base_config["agents"][name] = {"config_file": str(agent_file.resolve())}

    config_path = project_dir / "config.toml"
    config_path.write_text('model = "gpt-5.4"\n', encoding="utf-8")
    return CodexProjectConfig(
        project_dir=project_dir.resolve(),
        config_path=config_path.resolve(),
        base_config=base_config,
        agent_files=agent_files,
    )


def test_format_task_input_uses_title_when_description_is_blank():
    assert CodexRunner.format_task_input("Build Tetris", "") == "Build Tetris"


def test_format_task_input_includes_title_and_description():
    assert CodexRunner.format_task_input("Build Tetris", "Use canvas and keyboard input") == (
        "Title: Build Tetris\nDescription: Use canvas and keyboard input"
    )


@pytest.mark.asyncio
async def test_run_codex_maps_sidecar_events(httpx_mock: HTTPXMock, tmp_path):
    runner = CodexRunner(
        base_url="http://127.0.0.1:8765",
        model="gpt-5.4",
        sandbox_mode="workspace-write",
        approval_policy="never",
        run_timeout_s=300,
        prompt_library=make_prompts(),
        policy=make_policy(),
        project_config=make_project_config(tmp_path),
    )
    events = "\n\n".join(
        [
            'data: {"type":"item.completed","item":{"type":"agent_message","text":"final text"}}',
            'data: {"type":"state","id":"run-1","status":"done"}',
        ]
    )
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/runs",
        json={"runId": "run-1"},
        status_code=200,
    )
    httpx_mock.add_response(
        method="GET",
        url="http://127.0.0.1:8765/runs/run-1/events",
        text=events,
        status_code=200,
    )

    seen = []

    async def capture(line: str):
        seen.append(line)

    exit_code, output = await runner.run_codex(
        "hello",
        tmp_path,
        log_callback=capture,
        task_id=12,
    )

    assert exit_code == 0
    assert output == "final text"
    assert seen == ["final text"]
    post_request = httpx_mock.get_requests()[0]
    body = json.loads(post_request.content.decode("utf-8"))
    assert body["workingDirectory"] == str(tmp_path)
    assert body["sandboxMode"] == "workspace-write"
    assert body["approvalPolicy"] == "never"
    assert body["timeoutMs"] == 300000


@pytest.mark.asyncio
async def test_run_codex_falls_back_to_sidecar_result_when_stream_has_only_terminal_state(
    httpx_mock: HTTPXMock, tmp_path
):
    runner = CodexRunner(
        base_url="http://127.0.0.1:8765",
        model="gpt-5.4",
        sandbox_mode="workspace-write",
        approval_policy="never",
        run_timeout_s=300,
        prompt_library=make_prompts(),
        policy=make_policy(),
        project_config=make_project_config(tmp_path),
    )
    events = 'data: {"type":"state","id":"run-2","status":"failed"}'
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/runs",
        json={"runId": "run-2"},
        status_code=200,
    )
    httpx_mock.add_response(
        method="GET",
        url="http://127.0.0.1:8765/runs/run-2/events",
        text=events,
        status_code=200,
    )
    httpx_mock.add_response(
        method="GET",
        url="http://127.0.0.1:8765/runs/run-2/events",
        json={
            "runId": "run-2",
            "status": "failed",
            "events": [],
            "result": "outputSchema must be a plain JSON object",
            "exitCode": 1,
        },
        status_code=200,
    )

    exit_code, output = await runner.run_codex(
        "hello",
        tmp_path,
        task_id=13,
    )

    assert exit_code == 1
    assert output == "outputSchema must be a plain JSON object"


@pytest.mark.asyncio
async def test_run_intake_returns_structured_payload(httpx_mock: HTTPXMock, tmp_path):
    runner = CodexRunner(
        base_url="http://127.0.0.1:8765",
        model="gpt-5.4",
        sandbox_mode="workspace-write",
        approval_policy="never",
        run_timeout_s=300,
        prompt_library=make_prompts(),
        policy=make_policy(),
        project_config=make_project_config(tmp_path),
    )
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/intake",
        json={
            "status": "ok",
            "response": {
                "draft": {
                    "workspace_mode": "new",
                    "workspace_id": None,
                    "new_workspace_name": "Build Tetris",
                    "title": "Build Tetris",
                    "description": "Create a Tetris game.",
                    "blocked_by_task_id": None,
                    "scheduled_for": None,
                },
                "questions": [],
                "needs_confirmation": True,
                "notes": ["Use a new workspace."],
            },
        },
        status_code=200,
    )

    payload = await runner.run_intake("analyze", cwd=tmp_path, output_schema={"type": "object"})

    assert payload["draft"]["title"] == "Build Tetris"
    assert payload["needs_confirmation"] is True
    post_request = httpx_mock.get_requests()[0]
    body = json.loads(post_request.content.decode("utf-8"))
    instructions_path = Path(body["config"]["model_instructions_file"])
    assert instructions_path.parent.name == ".generated"
    assert instructions_path.name == "intake.md"
    assert "intake instructions" in instructions_path.read_text(encoding="utf-8")
    assert body["config"]["features"]["multi_agent"] is False


@pytest.mark.asyncio
async def test_cancel_posts_remote_cancel(httpx_mock: HTTPXMock, tmp_path):
    runner = CodexRunner(
        base_url="http://127.0.0.1:8765",
        model="gpt-5.4",
        sandbox_mode="workspace-write",
        approval_policy="never",
        run_timeout_s=300,
        prompt_library=make_prompts(),
        policy=make_policy(),
        project_config=make_project_config(tmp_path),
    )
    runner._task_runs[5] = "run-5"
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/runs/run-5/cancel",
        json={"ok": True},
        status_code=200,
    )

    await runner.cancel(5)

    assert 5 not in runner._task_runs


@pytest.mark.asyncio
async def test_generate_plan_uses_project_prompt_library(httpx_mock: HTTPXMock, tmp_path):
    runner = CodexRunner(
        base_url="http://127.0.0.1:8765",
        model="gpt-5.4",
        sandbox_mode="workspace-write",
        approval_policy="never",
        run_timeout_s=300,
        prompt_library=make_prompts(),
        policy=make_policy(),
        project_config=make_project_config(tmp_path),
    )
    events = "\n\n".join(
        [
            'data: {"type":"item.completed","item":{"type":"agent_message","text":"ok"}}',
            'data: {"type":"state","id":"run-1","status":"done"}',
        ]
    )
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/runs",
        json={"runId": "run-1"},
        status_code=200,
    )
    httpx_mock.add_response(
        method="GET",
        url="http://127.0.0.1:8765/runs/run-1/events",
        text=events,
        status_code=200,
    )

    await runner.generate_plan(
        tmp_path,
        "Build Tetris",
        repo_name="demo",
        workspace_name="Main",
        branch_name="workspace/main/1",
        base_branch="main",
    )

    post_request = httpx_mock.get_requests()[0]
    body = json.loads(post_request.content.decode("utf-8"))
    assert body["prompt"] == "PLAN::Build Tetris"
    instructions_path = Path(body["config"]["model_instructions_file"])
    assert instructions_path.parent.name == ".generated"
    assert instructions_path.name == "planner.md"
    assert "planner instructions" in instructions_path.read_text(encoding="utf-8")
    assert body["config"]["features"]["multi_agent"] is False


def test_sidecar_manager_allowlist_env_does_not_forward_global_auth(tmp_path, monkeypatch):
    settings = SimpleNamespace(
        CODEX_SDK_HOME=tmp_path / "home",
        CODEX_SDK_CONFIG_FILE=tmp_path / "home" / "config.toml",
        CODEX_SDK_AUTH_FILE=tmp_path / "home" / "auth.json",
    )
    manager = CodexSidecarManager(settings)

    monkeypatch.setenv("OPENAI_API_KEY", "should-not-leak")
    monkeypatch.setenv("CODEX_HOME", "should-not-leak")
    monkeypatch.setenv("PATH", "C:\\Windows\\System32")

    env = manager._allowlist_env()

    assert env["CODEX_HOME"] == str(settings.CODEX_SDK_HOME)
    assert "OPENAI_API_KEY" not in env
    assert env["HOME"] == str(settings.CODEX_SDK_HOME)


def test_sidecar_manager_writes_project_local_oauth_config(tmp_path):
    settings = SimpleNamespace(
        CODEX_SDK_HOME=tmp_path / "home",
        CODEX_SDK_CONFIG_FILE=tmp_path / "home" / "config.toml",
        CODEX_SDK_AUTH_FILE=tmp_path / "home" / "auth.json",
    )
    manager = CodexSidecarManager(settings)

    manager._ensure_runtime_files()

    assert settings.CODEX_SDK_CONFIG_FILE.exists()
    assert 'forced_login_method = "chatgpt"' in settings.CODEX_SDK_CONFIG_FILE.read_text(encoding="utf-8")
