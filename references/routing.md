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

## Configuration priority

1. explicit CLI flags
2. canonical `HENRY_IMAGE_*` environment variables

There is no fallback to legacy names.
