{{ config(tags=['stub']) }}
-- PHONE_INVALID · validity · Milestone 2 · YOUR CHECK
--
-- Phone numbers that cannot be a real number in any of the partner formats.
-- Spec, gotchas and hints: docs/defect-catalog.md#phone_invalid
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_phone_invalid+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
