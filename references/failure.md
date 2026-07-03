# Failure Handling

## Principles

- state the exact blocker
- do not ask for secrets in chat
- do not pretend a missing route is working
- do not return prompt output unless prompt output was requested or image delivery is blocked

## Common blockers

- missing configuration
- invalid credentials
- validation error
- network error
- service unavailable
- no image result
- rate limited or quota limited

## Next action shape

- configuration issue: set the missing value and rerun
- validation issue: fix the command input and rerun
- network issue: retry after confirming the endpoint
- service issue: wait for recovery, then rerun
- repeated exact-dimension failure: switch to SVG, PDF, or a written spec
