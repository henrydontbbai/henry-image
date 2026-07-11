# Routing

## Choose the mode

- new image -> `generate`
- revise existing image -> `edit`
- many tasks -> `batch`
- prompt output only -> `prompt`
- readiness check -> `probe`

## Choose the route

- `responses` when the configured response route is your preferred path and can return image bytes
- `images` when the configured image route is the direct path
- `auto` when both are configured and Henry Image should try `responses` first, then fall back to `images` only for retryable remote failures

## Route contract

- `responses` requires `model`
- `images` requires `image-model`
- `auto` requires both
- `responses` and `auto` require `--n 1`
- use `images` when requesting multiple outputs

## Fallback policy for `auto`

`auto` may fall back from `responses` to `images` for:

- `api_error`
- `network_error`
- `server_error`
- `not_found`
- `timeout`
- `no_image_result`

`auto` does not fall back for:

- `invalid_credentials`
- `missing_credentials`
- `content_policy`
- `quota_exceeded`
- `rate_limited`
- `validation_error`
- `bad_parameter`
- `missing_configuration`

Authenticated API requests follow redirects only when scheme, hostname, and effective port remain the same. Image downloads may follow cross-origin HTTP(S) CDN redirects only through public addresses; they reject HTTPS downgrade, non-HTTP(S) schemes, and loopback, private, link-local, multicast, reserved, or other non-public targets.

## Configuration priority

1. explicit CLI flags
2. canonical `HENRY_IMAGE_*` environment variables

There is no fallback to legacy names.
