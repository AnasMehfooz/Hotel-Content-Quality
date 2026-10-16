{{ config(tags=['stub']) }}
-- URL_INVALID · validity · Milestone 2 · YOUR CHECK
--
-- Website values that are not a usable URL (typos in the scheme, spaces, placeholders).
-- Spec, gotchas and hints: docs/defect-catalog.md#url_invalid
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_url_invalid+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
