# Phase 2: Coverage Expansion - Context

**Gathered:** 2026-04-19
**Status:** Complete

## Phase Boundary

Add focused tests for low-cost, high-risk branches without introducing live provider or OCR binary dependencies.

## Decisions

- Use monkeypatches and stubs for provider, OCR, terminal, and filesystem behavior.
- Raise the repository coverage gate only after the suite confirms stable headroom.
- Prioritize critical policy modules and broad behavior over chasing every unreachable branch in the large pipeline.
