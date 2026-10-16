{{ config(tags=['stub']) }}
-- ADDRESS_CITY_MISMATCH · consistency · Milestone 3 · YOUR CHECK
--
-- A postcode or phone area code that belongs to the other city.
-- Spec, gotchas and hints: docs/defect-catalog.md#address_city_mismatch
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_address_city_mismatch+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
