{{ config(tags=['stub']) }}
-- WRONG_MAPPING · accuracy · Milestone 3 · YOUR CHECK
--
-- A listing linked to the wrong master hotel in the mapping table.
-- Spec, gotchas and hints: docs/defect-catalog.md#wrong_mapping
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_wrong_mapping+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
