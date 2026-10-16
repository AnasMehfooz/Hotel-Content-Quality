{{ config(tags=['stub']) }}
-- GEO_OFFSET · accuracy · Milestone 3 · YOUR CHECK
--
-- Coordinates far away from the mapped master hotel.
-- Spec, gotchas and hints: docs/defect-catalog.md#geo_offset
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_geo_offset+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
