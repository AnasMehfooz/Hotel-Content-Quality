"""The defect catalog exists in three places; they must agree."""

import csv

import yaml

from hcq.config import PROJECT_ROOT
from hcq.generator.catalog import DEFECTS, INCIDENTS


def test_codes_match_dbt_registry_and_union_list():
    with (PROJECT_ROOT / "dbt" / "seeds" / "dq_checks.csv").open(encoding="utf-8") as fh:
        seed_codes = {row["check_code"] for row in csv.DictReader(fh)}
    project = yaml.safe_load((PROJECT_ROOT / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))
    union_codes = {m.upper().removeprefix("DQ_") for m in project["vars"]["dq_checks"]}
    assert set(DEFECTS) == seed_codes == union_codes


def test_every_check_has_a_model_file():
    checks = PROJECT_ROOT / "dbt" / "models" / "dq" / "checks"
    for code in DEFECTS:
        name = f"dq_{code.lower()}"
        assert (checks / f"{name}.sql").exists() or (checks / f"{name}.py").exists(), name


def test_incidents_reference_known_defects():
    assert {i.defect for i in INCIDENTS} <= set(DEFECTS)
    for incident in INCIDENTS:
        start, end = incident.days(10)
        assert 0 <= start <= end <= 9
