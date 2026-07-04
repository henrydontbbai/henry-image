# Runbooks

## Long prompt or large job

Use `--background-job`, then monitor with:

- `job-status`
- `job-diagnose`
- `job-cancel`

## Batch work

Use `batch` with JSONL input when many prompts or revisions share the same configuration.

## Job recovery flow

1. inspect `job-status`
2. add `--diagnose` or run `job-diagnose --format human`
3. reuse `replay_command` after fixing the blocker
4. clean up stale jobs with `job-cleanup`

## Stored status note

`job-list` reports the saved job metadata on disk. It does not probe live processes in real time.

## Upstream timeout

If the remote service times out, Henry Image reports a structured `timeout` error. Treat the timeout as a remote availability problem unless a local validation error explains it first.

## Repeatable recovery

Use the emitted `replay_command` as the starting point for the next retry.
