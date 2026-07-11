# Changelog

## 1.0.1 - 2026-07-11

- restrict authenticated API redirects to the same origin and harden image downloads against unsafe schemes, HTTPS downgrade, and URLs resolving to non-public addresses
- validate base URLs, successful response objects, image signatures, Images API parameters, and multi-output route compatibility with structured errors
- commit image files and manifests atomically with rollback when overwrite or multi-file submission fails
- bind background jobs to platform process identities and expose safe cancellation outcomes without signalling unverified legacy jobs
- preserve reliability and batch arguments in platform-compatible replay commands without exposing API key values
- synchronize security support, validation, tests, and public documentation with the `1.0.1` release contract
- reject background dry-run ambiguity, structure malformed success/output errors, atomically persist job metadata, and cover Python 3.9/macOS in CI

## 1.0.0 - 2026-07-05

- remove low-value public CLI tuning flags: `--images-compat`, `--input-fidelity`, `--background`, `--moderation`, `--partial-images`, and `--retries`
- keep `--images-response-format` and `--output-compression` as the remaining public route-specific advanced images options
- update public docs and local validation so help output, references, and repository checks match the `1.0.0` CLI surface

## 0.2.6 - 2026-07-04

- preserve `request_id` and route metadata when remote image base64 is malformed
- return a structured Henry `validation_error` instead of surfacing low-level decode failures
- add a CLI contract test confirming `generate --dry-run` works without `HENRY_IMAGE_API_KEY`

## 0.2.5 - 2026-07-04

- return structured `validation_error` output for local prompt and argument failures instead of Python tracebacks
- lock `auto` fallback behavior with contract tests for retryable and non-retryable categories
- add request-layer regression coverage for transport wrapping and failure classification
- clarify the public output contract, including stable metadata fields and the diagnostic status of `workflow_profile`
- expand public docs for first run, batch input, job recovery, and upstream timeout handling
- add maintainer-facing `CONTRIBUTING.md`, `SECURITY.md`, and minimal issue / pull request templates

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
