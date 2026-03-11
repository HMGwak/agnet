import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
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
            "explore": SimpleNamespace(substitute=lambda context: f"EXPLORE::{context['task_input']}"),
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
            "orchestrate": SimpleNamespace(
                substitute=lambda context: f"ORCHESTRATE::{context['current_phase']}::{context['task_input']}"
            ),
            "recover": SimpleNamespace(
                substitute=lambda context: f"RECOVER::{context['plan_text']}::{context['task_input']}"
            ),
            "verify": SimpleNamespace(
                substitute=lambda context: f"VERIFY::{context['plan_text']}::{context['task_input']}"
            ),
        }
    )


def make_project_config(tmp_path: Path) -> CodexProjectConfig:
    contract_dir = tmp_path / "runtime" / "codex" / "contract"
    generated_dir = tmp_path / "runtime" / "codex" / "generated"
    agent_dir = contract_dir / "agents"
    instructions_dir = contract_dir / "instructions"
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
    for name, multi_agent, model in (
        ("intake", False, "gpt-5.4"),
        ("orchestrator", False, "gpt-5.4"),
        ("explorer", False, "gpt-5.3-codex-spark"),
        ("planner", False, "gpt-5.4"),
        ("critic", False, "gpt-5.4"),
        ("executor", True, "gpt-5-codex"),
        ("tester", False, "gpt-5-codex"),
        ("reviewer", False, "gpt-5.4"),
        ("recovery_planner", False, "gpt-5.4"),
        ("verifier", False, "gpt-5.4"),
    ):
        instruction_file = instructions_dir / f"{name}.md"
        instruction_file.write_text(f"{name} instructions", encoding="utf-8")
        agent_file = agent_dir / f"{name}.toml"
        agent_file.write_text(
            "\n".join(
                [
                    f'model = "{model}"',
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

    config_path = contract_dir / "config.toml"
    config_path.write_text('model = "gpt-5.4"\n', encoding="utf-8")
    return CodexProjectConfig(
        contract_dir=contract_dir.resolve(),
        config_path=config_path.resolve(),
        generated_dir=generated_dir.resolve(),
        base_config=base_config,
        agent_files=agent_files,
    )


def make_sidecar_settings(tmp_path: Path) -> SimpleNamespace:
    sidecar_dir = tmp_path / "runtime" / "codex" / "sidecar"
    project_dir = tmp_path / "project"
    home_dir = tmp_path / "runtime" / "codex" / "home"
    logs_dir = tmp_path / "project" / "logs"
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        PROJECT_DATA_DIR=project_dir,
        CODEX_HOME_DIR=home_dir,
        CODEX_HOME_CONFIG_FILE=home_dir / "config.toml",
        CODEX_AUTH_FILE=home_dir / "auth.json",
        CODEX_SIDECAR_DIR=sidecar_dir,
        CODEX_SIDECAR_ENTRYPOINT=sidecar_dir / "server.mjs",
        CODEX_SIDECAR_HOST="127.0.0.1",
        CODEX_SIDECAR_PORT=8765,
        SESSION_LOGS_DIR=logs_dir / "session",
        TASK_LOGS_DIR=logs_dir / "session" / "tasks",
        SESSION_METADATA_FILE=logs_dir / "session" / "session.json",
    )


class HangingSSEStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk
        await asyncio.sleep(3600)

    async def aclose(self) -> None:
        return None


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
async def test_run_codex_returns_final_output_when_stream_stalls_after_agent_message(
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
        final_output_idle_timeout_s=0.01,
    )
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/runs",
        json={"runId": "run-3"},
        status_code=200,
    )
    httpx_mock.add_callback(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=HangingSSEStream(
                [b'data: {"type":"item.completed","item":{"type":"agent_message","text":"final text"}}\n\n']
            ),
        ),
        method="GET",
        url="http://127.0.0.1:8765/runs/run-3/events",
    )
    httpx_mock.add_response(
        method="GET",
        url="http://127.0.0.1:8765/runs/run-3/events",
        json={
            "runId": "run-3",
            "status": "running",
            "events": [
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "final text"},
                }
            ],
            "result": None,
            "exitCode": None,
        },
        status_code=200,
    )
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/runs/run-3/cancel",
        json={"runId": "run-3", "status": "cancelled"},
        status_code=200,
    )

    exit_code, output = await runner.run_codex(
        "hello",
        tmp_path,
        task_id=14,
    )

    assert exit_code == 0
    assert output == "final text"


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
    assert body["model"] == "gpt-5.4"
    instructions_path = Path(body["config"]["model_instructions_file"])
    assert instructions_path.parent.name == "generated"
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
    assert body["model"] == "gpt-5.4"
    assert body["prompt"] == "PLAN::Build Tetris"
    instructions_path = Path(body["config"]["model_instructions_file"])
    assert instructions_path.parent.name == "generated"
    assert instructions_path.name == "planner.md"
    assert "planner instructions" in instructions_path.read_text(encoding="utf-8")
    assert body["config"]["features"]["multi_agent"] is False


@pytest.mark.asyncio
async def test_explore_repo_uses_agent_specific_model(httpx_mock: HTTPXMock, tmp_path):
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
            'data: {"type":"state","id":"run-9","status":"done"}',
        ]
    )
    httpx_mock.add_response(
        method="POST",
        url="http://127.0.0.1:8765/runs",
        json={"runId": "run-9"},
        status_code=200,
    )
    httpx_mock.add_response(
        method="GET",
        url="http://127.0.0.1:8765/runs/run-9/events",
        text=events,
        status_code=200,
    )

    await runner.explore_repo(
        tmp_path,
        "Build Tetris",
        repo_name="demo",
        workspace_name="Main",
        branch_name="workspace/main/1",
        base_branch="main",
    )

    post_request = httpx_mock.get_requests()[0]
    body = json.loads(post_request.content.decode("utf-8"))
    assert body["model"] == "gpt-5.3-codex-spark"
    assert body["config"]["model"] == "gpt-5.3-codex-spark"


def test_sidecar_manager_allowlist_env_does_not_forward_global_auth(tmp_path, monkeypatch):
    settings = make_sidecar_settings(tmp_path)
    manager = CodexSidecarManager(settings)

    monkeypatch.setenv("OPENAI_API_KEY", "should-not-leak")
    monkeypatch.setenv("CODEX_HOME", "should-not-leak")
    monkeypatch.setenv("PATH", "C:\\Windows\\System32")

    env = manager._allowlist_env()

    assert env["CODEX_HOME"] == str(settings.CODEX_HOME_DIR)
    assert "OPENAI_API_KEY" not in env
    assert env["HOME"] == str(settings.CODEX_HOME_DIR)


def test_sidecar_manager_writes_repository_local_oauth_config(tmp_path):
    settings = make_sidecar_settings(tmp_path)
    manager = CodexSidecarManager(settings)

    manager._ensure_runtime_files()

    assert settings.CODEX_HOME_CONFIG_FILE.exists()
    assert 'forced_login_method = "chatgpt"' in settings.CODEX_HOME_CONFIG_FILE.read_text(encoding="utf-8")


def test_sidecar_manager_migrates_project_app_auth_into_repository_local_runtime_home(tmp_path):
    settings = make_sidecar_settings(tmp_path)
    manager = CodexSidecarManager(settings)
    legacy_home = settings.PROJECT_DATA_DIR / "app-codex-home"
    legacy_home.mkdir(parents=True, exist_ok=True)
    legacy_auth = legacy_home / "auth.json"
    legacy_auth.write_text('{"access_token":"legacy-app"}', encoding="utf-8")

    manager._ensure_runtime_files()

    assert settings.CODEX_AUTH_FILE.exists()
    assert settings.CODEX_AUTH_FILE.read_text(encoding="utf-8") == '{"access_token":"legacy-app"}'


def test_sidecar_manager_migrates_project_legacy_auth_when_app_auth_is_missing(tmp_path):
    settings = make_sidecar_settings(tmp_path)
    manager = CodexSidecarManager(settings)
    legacy_home = settings.PROJECT_DATA_DIR / "codex-home"
    legacy_home.mkdir(parents=True, exist_ok=True)
    legacy_auth = legacy_home / "auth.json"
    legacy_auth.write_text('{"access_token":"legacy"}', encoding="utf-8")

    manager._ensure_runtime_files()

    assert settings.CODEX_AUTH_FILE.exists()
    assert settings.CODEX_AUTH_FILE.read_text(encoding="utf-8") == '{"access_token":"legacy"}'


@pytest.mark.asyncio
async def test_sidecar_manager_start_rejects_non_local_codex_path(tmp_path, monkeypatch):
    settings = make_sidecar_settings(tmp_path)
    manager = CodexSidecarManager(settings)
    external_path = (tmp_path / "external" / "codex.exe").resolve()

    async def fake_health():
        return True, "READY", {
            "status": "READY",
            "codexPath": str(external_path),
            "runtimeHome": str(settings.CODEX_HOME_DIR),
        }

    monkeypatch.setattr(manager, "_health", fake_health)

    with pytest.raises(RuntimeError, match="repository-local Codex runtime"):
        await manager.start()


@pytest.mark.asyncio
async def test_sidecar_manager_start_rejects_non_local_runtime_home(tmp_path, monkeypatch):
    settings = make_sidecar_settings(tmp_path)
    manager = CodexSidecarManager(settings)
    local_codex_path = (
        settings.CODEX_SIDECAR_DIR / "node_modules" / ".bin" / "codex.cmd"
    ).resolve()
    wrong_runtime_home = (tmp_path / "other-home").resolve()

    async def fake_health():
        return True, "READY", {
            "status": "READY",
            "codexPath": str(local_codex_path),
            "runtimeHome": str(wrong_runtime_home),
        }

    monkeypatch.setattr(manager, "_health", fake_health)

    with pytest.raises(RuntimeError, match="repository-local runtime home"):
        await manager.start()


def test_sidecar_manager_updates_session_metadata_with_runtime_details(tmp_path):
    settings = make_sidecar_settings(tmp_path)
    manager = CodexSidecarManager(settings)
    settings.SESSION_METADATA_FILE.parent.mkdir(parents=True)
    settings.SESSION_METADATA_FILE.write_text(
        json.dumps({"session_id": "260308_120000", "processes": {}}),
        encoding="utf-8",
    )
    manager.process = SimpleNamespace(pid=4321)
    codex_path = str(
        (settings.CODEX_SIDECAR_DIR / "node_modules" / ".bin" / "codex.cmd").resolve()
    )

    manager._update_session_metadata(
        {"codexPath": codex_path, "runtimeHome": str(settings.CODEX_HOME_DIR)}
    )

    metadata = json.loads(settings.SESSION_METADATA_FILE.read_text(encoding="utf-8"))
    assert metadata["processes"]["sidecar"] == 4321
    assert metadata["codex_path"] == codex_path
    assert metadata["runtime_home"] == str(settings.CODEX_HOME_DIR)
