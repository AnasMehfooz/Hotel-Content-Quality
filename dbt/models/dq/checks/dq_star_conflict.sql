{{ config(tags=['stub']) }}
-- STAR_CONFLICT · consistency · Milestone 3 · YOUR CHECK
--
-- A star rating that contradicts the master catalog by more than legitimate noise.
-- Spec, gotchas and hints: docs/defect-catalog.md#star_conflict
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_star_conflict+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
