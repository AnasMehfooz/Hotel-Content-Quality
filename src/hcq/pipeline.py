"""Run dbt and read results. dbt runs in a subprocess so DuckDB locks never leak into this process."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import duckdb

from hcq.config import Settings


def dbt_executable() -> str:
    candidate = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("dbt")
    if not found:
        raise RuntimeError("dbt is not installed in this environment. Run `uv sync`.")
    return found


def run_dbt(settings: Settings, *args: str, quiet: bool = False) -> int:
    """Run a dbt command against this project. Returns dbt's exit code."""
    settings.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **settings.dbt_env()}
    # the dedup Python model reads these through hcq.config
    env.update(
        HCQ_EMBEDDINGS=settings.embeddings,
        HCQ_EMBED_MODEL=settings.embed_model,
        HCQ_OLLAMA_URL=settings.ollama_url,
    )
    env["DBT_TARGET_PATH"] = str(settings.dbt_target_path())
    env["DBT_LOG_PATH"] = str(settings.dbt_target_path() / "logs")
    env.setdefault("DBT_SEND_ANONYMOUS_USAGE_STATS", "false")
    cmd = [
        dbt_executable(),
        *args,
        "--project-dir",
        str(settings.dbt_dir),
        "--profiles-dir",
        str(settings.dbt_dir),
    ]
    # cwd = the dbt folder's parent: dbt-duckdb resolves seed paths relative to the working directory
    result = subprocess.run(
        cmd, env=env, cwd=settings.dbt_dir.parent, capture_output=quiet, text=True, check=False
    )
    if quiet and result.returncode != 0:
        sys.stderr.write(result.stdout[-4000:] + result.stderr[-2000:])
    return result.returncode


@contextmanager
def warehouse(settings: Settings, read_only: bool = True):
    if not settings.warehouse_path.exists():
        raise FileNotFoundError(
            f"{settings.warehouse_path} not found. Run `hcq demo` or `hcq build` first."
        )
    con = duckdb.connect(str(settings.warehouse_path), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def dbt_manifest(settings: Settings) -> dict:
    path = settings.dbt_target_path() / "manifest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def stub_check_codes(settings: Settings) -> set[str]:
    """Check codes whose dbt model still carries the ``stub`` tag (not implemented yet)."""
    nodes = dbt_manifest(settings).get("nodes", {})
    return {
        node["name"].upper().removeprefix("DQ_")
        for node in nodes.values()
        if node.get("resource_type") == "model" and "stub" in node.get("tags", [])
    }
