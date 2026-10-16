{{ config(tags=['stub']) }}
-- PRICE_OUTLIER · plausibility · Milestone 4 · YOUR CHECK
--
-- Nightly rates that cannot be right (rate grain: set stay_date).
-- Spec, gotchas and hints: docs/defect-catalog.md#price_outlier
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_price_outlier+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
