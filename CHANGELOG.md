# Changelog

## 0.2.1 - 2026-07-04

- convert remote request timeouts into structured CLI errors instead of Python tracebacks
- handle remote edit-input download timeouts through the same structured error path
- add troubleshooting guidance for upstream timeout behavior

## 0.2.0 - 2026-07-04

- removed legacy naming and host-specific fallback behavior
- narrowed public configuration to four canonical `HENRY_IMAGE_*` variables
- removed retired public commands and flags
- renamed the local agent file to `agents/henry-image.yaml`
- refreshed docs for a Henry-only public surface
- added MIT license, `.env.example`, and public quickstart guidance
- strengthened CI with layered jobs and a Python `3.11` / `3.12` matrix
- added release-process documentation and local release checks
