# Henry Image 0.2.0 Public Cleanup Plan

## Goal

Prepare a public-safe Henry Image release with a narrow configuration contract, neutral wording, and a minimal release surface.

## Required outcomes

- only the four public `HENRY_IMAGE_*` variables remain
- route and model validation is explicit
- public text is Henry-only
- old agent naming is removed
- local checks and CI pass

## Release checklist

1. keep the CLI surface limited to the supported commands
2. keep prompt output generic
3. keep diagnostics neutral
4. ship `LICENSE`, `CHANGELOG.md`, and CI
5. pass `pytest` and `quick_validate`
