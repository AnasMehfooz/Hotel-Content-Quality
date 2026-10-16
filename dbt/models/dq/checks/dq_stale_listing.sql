{{ config(tags=['stub']) }}
-- STALE_LISTING · timeliness · Milestone 3 · YOUR CHECK
--
-- A listing whose last update is far older than the partner's refresh cycle.
-- Spec, gotchas and hints: docs/defect-catalog.md#stale_listing
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_stale_listing+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
