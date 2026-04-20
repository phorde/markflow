# Phase 3 Summary: Golden Regressions

## Status

Complete.

## Accomplishments

- Added deterministic golden functional tests in `tests/functional/test_golden_regressions.py`.
- Covered text-native PDF output, table preservation, local OCR report metadata, invalid-page document failure, and malicious HTML sanitization.

## Verification

- `pytest -m functional -q --no-cov`
- Full suite and coverage gates included in final validation.
