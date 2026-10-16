{{ config(tags=['stub']) }}
-- ENCODING_MOJIBAKE · validity · Milestone 2 · YOUR CHECK
--
-- Text that was UTF-8 but got decoded as Windows-1252 (Köln -> KÃ¶ln).
-- Spec, gotchas and hints: docs/defect-catalog.md#encoding_mojibake
-- Contract: return the columns of dq_empty() (enforced in _checks.yml). See dq_missing_required.sql.
-- Workflow: delete the config line above, replace the select below, then run
--   hcq build --select dq_encoding_mojibake+    and    hcq progress
-- until the check meets its precision and recall targets.

{{ dq_empty() }}
