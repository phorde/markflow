# Phase 3: Golden Regressions - Context

**Gathered:** 2026-04-19
**Status:** Complete

## Phase Boundary

Add deterministic functional regressions for representative document classes while avoiding real sensitive documents and live OCR/LLM dependencies.

## Decisions

- Generate fixture PDFs inside tests with PyMuPDF.
- Stub page processing to make golden markdown/report/HTML assertions deterministic.
- Cover text-native, table, local OCR, invalid page, and malicious payload scenarios.
