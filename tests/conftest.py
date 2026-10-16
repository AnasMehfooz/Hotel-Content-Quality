"""Shared fixtures: a small simulated window built into a temp folder, once per test session."""

from __future__ import annotations

from datetime import date

import pytest

from hcq.config import Settings
from hcq.generator import FeedBuild, generate_feeds
from hcq.pipeline import run_dbt
from hcq.reference import build_reference

END_DATE = date(2026, 10, 15)


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    root = tmp_path_factory.mktemp("hcq")
    return Settings(
        data_dir=root / "data",
        reports_dir=root / "reports",
        dbt_target=root / "dbt_target",
        seed=7,
        days=10,
        end_date=END_DATE,
        reference="synthetic",
        embeddings="off",
    )


@pytest.fixture(scope="session")
def feeds(settings: Settings) -> FeedBuild:
    build_reference(settings, "synthetic")
    return generate_feeds(settings)


@pytest.fixture(scope="session")
def built(settings: Settings, feeds: FeedBuild) -> Settings:
    """Feeds -> dbt build in the temp warehouse, using the checks as they are in your repo."""
    code = run_dbt(settings, "build", quiet=True)
    assert code == 0, "dbt build failed; run `hcq build` to see the error"
    return settings
