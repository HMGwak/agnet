import os
from types import SimpleNamespace

import pytest

from app.services.codex_agent import CodexAgent


def test_resolve_command_prefers_windows_launcher(monkeypatch):
    agent = CodexAgent("codex")

    def fake_which(cmd: str) -> str | None:
        if cmd == "codex.cmd":
            return r"C:\Users\plane\AppData\Roaming\npm\codex.cmd"
        return None

    monkeypatch.setattr("app.services.codex_agent.shutil.which", fake_which)
    monkeypatch.setattr("app.services.codex_agent.os.name", "nt")

    assert agent._resolve_command() == [r"C:\Users\plane\AppData\Roaming\npm\codex.cmd"]


def test_build_exec_command_uses_exec_mode(monkeypatch):
    agent = CodexAgent("codex")

    monkeypatch.setattr(agent, "_resolve_command", lambda: ["codex.cmd"])

    assert agent._build_exec_command("hello") == [
        "codex.cmd",
        "exec",
        "--full-auto",
        "--color",
        "never",
        "-",
    ]


def test_format_task_input_uses_title_when_description_is_blank():
    assert CodexAgent.format_task_input("Build Tetris", "") == "Build Tetris"


def test_format_task_input_includes_title_and_description():
    assert CodexAgent.format_task_input("Build Tetris", "Use canvas and keyboard input") == (
        "Title: Build Tetris\nDescription: Use canvas and keyboard input"
    )


@pytest.mark.asyncio
async def test_run_codex_writes_prompt_to_stdin(monkeypatch, tmp_path):
    written = bytearray()

    class FakeStdin:
        def write(self, data: bytes):
            written.extend(data)

        async def drain(self):
            return None

        def close(self):
            return None

    class FakeStdout:
        def __aiter__(self):
            async def gen():
                yield b"done\n"

            return gen()

    class FakeProc:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeStdout()
            self.returncode = 0

        async def wait(self):
            return 0

    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeProc()

    agent = CodexAgent("codex")
    monkeypatch.setattr(agent, "_resolve_command", lambda: ["codex.cmd"])
    monkeypatch.setattr(
        "app.services.codex_agent.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    exit_code, output = await agent.run_codex("hello from stdin", tmp_path)

    assert exit_code == 0
    assert output == "done"
    assert captured["args"] == ("codex.cmd", "exec", "--full-auto", "--color", "never", "-")
    assert captured["kwargs"]["stdin"] is not None
    assert bytes(written) == b"hello from stdin"
