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
        runtime_home = self.settings.CODEX_HOME_DIR
        runtime_home.mkdir(parents=True, exist_ok=True)
        (runtime_home / "AppData" / "Roaming").mkdir(parents=True, exist_ok=True)
        (runtime_home / "AppData" / "Local").mkdir(parents=True, exist_ok=True)
        config_file = self.settings.CODEX_HOME_CONFIG_FILE
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

    def _update_session_metadata(self, health: dict[str, object] | None = None) -> None:
        metadata_path = self.settings.SESSION_METADATA_FILE
        if not metadata_path.exists():
            return
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        metadata.setdefault("processes", {})
        if self.process is not None:
            metadata["processes"]["sidecar"] = self.process.pid
        if isinstance(health, dict):
            codex_path = health.get("codexPath")
            runtime_home = health.get("runtimeHome")
            if isinstance(codex_path, str):
                metadata["codex_path"] = codex_path
            if isinstance(runtime_home, str):
                metadata["runtime_home"] = runtime_home
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _is_local_codex_path(self, codex_path: str | None) -> bool:
        if not codex_path:
            return False
        try:
            return Path(codex_path).resolve().is_relative_to(
                self.settings.CODEX_SIDECAR_DIR.resolve()
            )
        except OSError:
            return False

    def _uses_expected_runtime_home(self, runtime_home: str | None) -> bool:
        if not runtime_home:
            return False
        try:
            return Path(runtime_home).resolve() == self.settings.CODEX_HOME_DIR.resolve()
        except OSError:
            return False

    def _validate_ready_payload(self, body: dict[str, object] | None) -> None:
        if not isinstance(body, dict):
            raise RuntimeError("Codex sidecar health check returned an invalid payload")

        codex_path = body.get("codexPath")
        if not isinstance(codex_path, str) or not self._is_local_codex_path(codex_path):
            raise RuntimeError(
                "Codex sidecar is not using the repository-local Codex runtime"
            )

        runtime_home = body.get("runtimeHome")
        if not isinstance(runtime_home, str) or not self._uses_expected_runtime_home(
            runtime_home
        ):
            raise RuntimeError(
                "Codex sidecar is not using the repository-local runtime home"
            )

    def _allowlist_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for key in ("PATH", "SystemRoot", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT", "COMSPEC"):
            value = os.environ.get(key)
            if value:
                env[key] = value

        runtime_home = self.settings.CODEX_HOME_DIR
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

    async def _health(self) -> tuple[bool, str | None, dict[str, object] | None]:
        url = f"http://{self.settings.CODEX_SIDECAR_HOST}:{self.settings.CODEX_SIDECAR_PORT}/health"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
            body = response.json()
            if not isinstance(body, dict):
                return False, None, None
            status = body.get("status")
            return status == "READY", status, body
        except Exception:
            return False, None, None

    async def start(self):
        healthy, _, body = await self._health()
        if healthy:
            self._validate_ready_payload(body)
            self._update_session_metadata(body)
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
            f"--runtime-home={self.settings.CODEX_HOME_DIR}",
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
            healthy, status, body = await self._health()
            if healthy:
                try:
                    self._validate_ready_payload(body)
                except RuntimeError:
                    await self.stop()
                    raise
                self._update_session_metadata(body)
                return
            if status == "AUTH_REQUIRED":
                await self.stop()
                raise RuntimeError(
                    f"Project-local Codex OAuth login is required. Run tools/codex-login and sign in to create {self.settings.CODEX_AUTH_FILE}."
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
