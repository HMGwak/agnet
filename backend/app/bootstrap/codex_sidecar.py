from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

import httpx


class CodexSidecarManager:
    def __init__(self, settings):
        self.settings = settings
        self.process: asyncio.subprocess.Process | None = None
        self._owns_process = False
        self._stdout_handle = None
        self._stderr_handle = None

    def _ensure_runtime_files(self) -> None:
        runtime_home = self.settings.CODEX_SDK_HOME
        runtime_home.mkdir(parents=True, exist_ok=True)
        (runtime_home / "AppData" / "Roaming").mkdir(parents=True, exist_ok=True)
        (runtime_home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
        config_file = self.settings.CODEX_SDK_CONFIG_FILE
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            'cli_auth_credentials_store = "file"\nforced_login_method = "chatgpt"\n',
            encoding="utf-8",
        )
        self.settings.SESSION_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.settings.TASK_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    def _open_log_handles(self) -> tuple[object, object]:
        self.settings.SESSION_LOGS_DIR.mkdir(parents=True, exist_ok=True)
        sidecar_out = self.settings.SESSION_LOGS_DIR / "sidecar.out.log"
        sidecar_err = self.settings.SESSION_LOGS_DIR / "sidecar.err.log"
        self._stdout_handle = open(sidecar_out, "ab")
        self._stderr_handle = open(sidecar_err, "ab")
        return self._stdout_handle, self._stderr_handle

    def _close_log_handles(self) -> None:
        for handle_attr in ("_stdout_handle", "_stderr_handle"):
            handle = getattr(self, handle_attr)
            if handle is not None:
                handle.close()
                setattr(self, handle_attr, None)

    def _update_session_metadata(self) -> None:
        metadata_path = self.settings.SESSION_METADATA_FILE
        if not metadata_path.exists() or self.process is None:
            return
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        metadata.setdefault("processes", {})
        metadata["processes"]["sidecar"] = self.process.pid
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _allowlist_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT", "COMSPEC"):
            value = os.environ.get(key)
            if value:
                env[key] = value

        runtime_home = self.settings.CODEX_SDK_HOME
        runtime_home.mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(runtime_home)
        env["USERPROFILE"] = str(runtime_home)
        env["CODEX_HOME"] = str(runtime_home)
        env["CODEX_RUNTIME_HOME"] = str(runtime_home)

        appdata = runtime_home / "AppData" / "Roaming"
        local_appdata = runtime_home / "AppData" / "Local"
        appdata.mkdir(parents=True, exist_ok=True)
        local_appdata.mkdir(parents=True, exist_ok=True)
        env["APPDATA"] = str(appdata)
        env["LOCALAPPDATA"] = str(local_appdata)

        drive, tail = os.path.splitdrive(str(runtime_home))
        if drive:
            env["HOMEDRIVE"] = drive
            env["HOMEPATH"] = tail or "\\"

        return env

    async def _health(self) -> tuple[bool, str | None]:
        url = f"http://{self.settings.CODEX_SIDECAR_HOST}:{self.settings.CODEX_SIDECAR_PORT}/health"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
            body = response.json()
            status = body.get("status")
            return status == "READY", status
        except Exception:
            return False, None

    async def start(self):
        healthy, _ = await self._health()
        if healthy:
            return

        node = shutil.which("node")
        if not node:
            raise RuntimeError("node is not installed or not on PATH")
        if not self.settings.CODEX_SIDECAR_ENTRYPOINT.exists():
            raise RuntimeError(f"Codex sidecar entrypoint not found: {self.settings.CODEX_SIDECAR_ENTRYPOINT}")

        self._ensure_runtime_files()
        env = self._allowlist_env()
        stdout_handle, stderr_handle = self._open_log_handles()
        self.process = await asyncio.create_subprocess_exec(
            node,
            str(self.settings.CODEX_SIDECAR_ENTRYPOINT),
            f"--host={self.settings.CODEX_SIDECAR_HOST}",
            f"--port={self.settings.CODEX_SIDECAR_PORT}",
            f"--runtime-home={self.settings.CODEX_SDK_HOME}",
            cwd=str(self.settings.CODEX_SIDECAR_DIR),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
        )
        self._owns_process = True
        self._update_session_metadata()

        for _ in range(50):
            if self.process.returncode is not None:
                self._close_log_handles()
                raise RuntimeError("Codex sidecar exited during startup")
            healthy, status = await self._health()
            if healthy:
                return
            if status == "AUTH_REQUIRED":
                await self.stop()
                raise RuntimeError(
                    f"Project-local Codex OAuth login is required. Run codex-login and sign in to create {self.settings.CODEX_SDK_AUTH_FILE}."
                )
            await asyncio.sleep(0.2)

        self._close_log_handles()
        raise RuntimeError("Codex sidecar did not become healthy in time")

    async def stop(self):
        if not self._owns_process or self.process is None or self.process.returncode is not None:
            self._close_log_handles()
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=5)
        except asyncio.TimeoutError:
            self.process.kill()
            await self.process.wait()
        self._close_log_handles()
