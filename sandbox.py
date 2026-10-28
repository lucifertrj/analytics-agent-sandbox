from __future__ import annotations

import atexit
import json
import os
import resource
import subprocess
import sys
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import polars as pl

import config


class Sandbox(ABC):
    @abstractmethod
    def run(self, code: str, csv_path: str) -> str:
        ...


_RUNNER = r"""
import json, sys, traceback
from pathlib import Path
import polars as pl

payload = json.load(sys.stdin)
namespace = {
    "pl": pl,
    "polars": pl,
    "Path": Path,
    "csv_path": payload["csv_path"],
    "__name__": "__main__",
}
try:
    exec(compile(payload["code"], "<generated_code>", "exec"), namespace)
except Exception:
    traceback.print_exc()
    sys.exit(1)
"""


def _daytona_preamble(remote_csv: str) -> str:
    return (
        "import json, sys, traceback\n"
        "from pathlib import Path\n"
        "import polars as pl\n"
        "polars = pl\n"
        f"csv_path = {remote_csv!r}\n"
        "__name__ = '__main__'\n"
    )


class DaytonaSandbox(Sandbox):
    def __init__(self) -> None:
        self._daytona = None
        self._sandbox = None
        self._uploaded: set[str] = set()
        self._polars_installed = False

    def _ensure_sandbox(self):
        if self._sandbox is not None:
            return self._sandbox

        try:
            from daytona import (
                CreateSandboxFromSnapshotParams,
                CreateSnapshotParams,
                Daytona,
                Image,
            )
        except ImportError as e:
            raise RuntimeError(
                "The 'daytona' package is required for SANDBOX_BACKEND=daytona. "
                "Install it with `uv pip install daytona` (or `pip install daytona`), "
                "or set SANDBOX_BACKEND=subprocess in config.py / the environment."
            ) from e

        if not os.getenv("DAYTONA_API_KEY"):
            raise RuntimeError(
                "DAYTONA_API_KEY is not set. Add it to your .env, or set "
                "SANDBOX_BACKEND=subprocess to run locally."
            )

        self._daytona = Daytona()

        # Create the sandbox from a snapshot that already has polars baked in,
        # so the slow `pip install` happens once (at snapshot-build time) instead
        # of on every cold start.
        snapshot_name = f"analytics-polars-{pl.__version__.replace('.', '-')}"
        if not self._snapshot_exists(snapshot_name):
            image = Image.debian_slim("3.12").pip_install(f"polars=={pl.__version__}")
            self._daytona.snapshot.create(
                CreateSnapshotParams(name=snapshot_name, image=image)
            )

        self._sandbox = self._daytona.create(
            CreateSandboxFromSnapshotParams(snapshot=snapshot_name)
        )
        atexit.register(self._cleanup)

        self._polars_installed = True
        return self._sandbox

    def _snapshot_exists(self, name: str) -> bool:
        page = 1
        while True:
            result = self._daytona.snapshot.list(page, 100)
            items = getattr(result, "items", result) or []
            if any(getattr(s, "name", None) == name for s in items):
                return True
            if len(items) < 100:
                return False
            page += 1

    def _ensure_csv(self, sandbox, csv_path: str) -> str:
        remote_csv = f"{config.DAYTONA_REMOTE_DIR}/{Path(csv_path).name}"
        if csv_path not in self._uploaded:
            data = Path(csv_path).read_bytes()
            sandbox.fs.upload_file(data, remote_csv)
            self._uploaded.add(csv_path)
        return remote_csv

    def run(self, code: str, csv_path: str) -> str:
        try:
            sandbox = self._ensure_sandbox()
            remote_csv = self._ensure_csv(sandbox, csv_path)
        except Exception as e:
            return f"Error preparing Daytona sandbox:\n{e}"

        full_code = _daytona_preamble(remote_csv) + "\n" + code
        try:
            response = sandbox.process.code_run(full_code, timeout=config.WALL_TIMEOUT)
        except Exception as e:
            return f"Error executing code in Daytona:\n{e}"

        output = (response.result or "").strip()
        if response.exit_code != 0:
            detail = output or f"process exited with code {response.exit_code}"
            return f"Error executing code:\n{detail}"
        if not output:
            return "Code executed successfully (no output produced). Remember to print() results."
        return output

    def _cleanup(self) -> None:
        if self._daytona is not None and self._sandbox is not None:
            try:
                self._daytona.delete(self._sandbox)
            except Exception:
                pass
            self._sandbox = None


def _apply_limits() -> None:
    resource.setrlimit(resource.RLIMIT_CPU, (config.CPU_SECONDS, config.CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (config.FSIZE_BYTES, config.FSIZE_BYTES))


class SubprocessSandbox(Sandbox):
    def run(self, code: str, csv_path: str) -> str:
        payload = json.dumps({"code": code, "csv_path": csv_path})
        preexec = _apply_limits if os.name == "posix" else None

        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", _RUNNER],
                input=payload,
                capture_output=True,
                text=True,
                timeout=config.WALL_TIMEOUT,
                preexec_fn=preexec,
            )
        except subprocess.TimeoutExpired:
            return (
                f"Error: code execution exceeded the {config.WALL_TIMEOUT}s time limit "
                "and was terminated. Simplify the query or avoid long loops."
            )
        except Exception as e:
            return f"Error launching execution subprocess:\n{e}\n{traceback.format_exc()}"

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            detail = stderr or stdout or f"process exited with code {proc.returncode}"
            return f"Error executing code:\n{detail}"

        result = stdout
        if stderr:
            result += f"\n\nStderr:\n{stderr}" if result else f"Stderr:\n{stderr}"
        if not result:
            result = "Code executed successfully (no output produced). Remember to print() results."
        return result


_INSTANCE: Optional[Sandbox] = None


def get_sandbox(backend: Optional[str] = None) -> Sandbox:
    global _INSTANCE
    backend = backend or config.SANDBOX_BACKEND
    if _INSTANCE is None:
        if backend == "daytona":
            _INSTANCE = DaytonaSandbox()
        else:
            _INSTANCE = SubprocessSandbox()
    return _INSTANCE
