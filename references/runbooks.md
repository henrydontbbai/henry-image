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

New jobs bind the PID to a Windows creation FILETIME or Linux `/proc` start time. A legacy job without identity can be monitored but returns `identity_unverified` from `job-cancel`. After a verified cancel, inspect `cancelled`, `cancel_pending`, or `cancel_failed` before cleanup.

Do not combine `--background-job` with `--dry-run`; the CLI rejects that combination before starting a child process. Invalid `job.json` files return `invalid_job_metadata` and are not cleaned automatically.

## Stored status note

`job-list` reports the saved job metadata on disk. It does not probe live processes in real time.

## Upstream timeout

If the remote service times out, Henry Image reports a structured `timeout` error. Treat the timeout as a remote availability problem unless a local validation error explains it first.

## Repeatable recovery

Use the emitted `replay_command` as the starting point for the next retry.

Replay preserves `--n`, `--timeout`, images response format, output compression, `--force`, and batch input. PowerShell and POSIX shells receive platform-compatible quoting, and API key values are never embedded.
