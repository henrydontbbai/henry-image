# Runbooks

## Long prompt or large job

Use `--background-job`, then monitor with:

- `job-status`
- `job-diagnose`
- `job-cancel`

## Batch work

Use `batch` with JSONL input when many prompts or revisions share the same configuration.

## Repeatable recovery

Use the emitted `replay_command` as the starting point for the next retry.
