import os

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
        "hello",
    ]
