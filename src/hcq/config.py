"""Runtime settings, resolved from environment variables (prefix ``HCQ_``) and ``.env``."""

from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(os.environ.get("HCQ_PROJECT_ROOT", Path(__file__).resolve().parents[2]))
TIMEZONE = ZoneInfo("Europe/Berlin")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HCQ_", env_file=PROJECT_ROOT / ".env", extra="ignore"
    )

    data_dir: Path = PROJECT_ROOT / "data"
    dbt_dir: Path = PROJECT_ROOT / "dbt"
    dbt_target: Path | None = None  # defaults to dbt/target
    reports_dir: Path = PROJECT_ROOT / "reports"

    # Feed simulation
    seed: int = 42
    days: int = 14
    end_date: date | None = None  # last snapshot day; defaults to today in Europe/Berlin
    reference: Literal["osm", "synthetic"] = "synthetic"

    # OpenStreetMap
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # Local LLM (Ollama)
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:14b"
    llm_think: bool | None = None  # only sent to Ollama when set (thinking models)
    embeddings: Literal["off", "ollama"] = "off"
    embed_model: str = "bge-m3"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def manifest_dir(self) -> Path:
        return self.raw_dir / "_manifest"

    @property
    def reference_dir(self) -> Path:
        return self.data_dir / "reference"

    @property
    def reference_path(self) -> Path:
        return self.reference_dir / "hotels.parquet"

    @property
    def warehouse_path(self) -> Path:
        return self.data_dir / "warehouse" / "hcq.duckdb"

    @property
    def tickets_path(self) -> Path:
        return self.data_dir / "warehouse" / "tickets.parquet"

    def dbt_target_path(self) -> Path:
        return self.dbt_target or self.dbt_dir / "target"

    def resolved_end_date(self) -> date:
        return self.end_date or datetime.now(TIMEZONE).date()

    def dbt_env(self) -> dict[str, str]:
        """Environment variables the dbt project reads (see dbt/profiles.yml and sources)."""
        return {
            "HCQ_RAW_DIR": self.raw_dir.resolve().as_posix(),
            "HCQ_REFERENCE_PATH": self.reference_path.resolve().as_posix(),
            "HCQ_MANIFEST_DIR": self.manifest_dir.resolve().as_posix(),
            "HCQ_DUCKDB_PATH": self.warehouse_path.resolve().as_posix(),
        }

    def export_env(self) -> None:
        """Make the dbt env vars visible to subprocesses (dbt, Dagster) of this process."""
        for key, value in self.dbt_env().items():
            os.environ[key] = value
        self.warehouse_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
