# Routing

## Choose the mode

- new image -> `generate`
- revise existing image -> `edit`
- many tasks -> `batch`
- prompt output only -> `prompt`
- readiness check -> `probe`

## Choose the route

- `responses` when the configured response route can return image bytes
- `images` when the configured image route is the direct path
- `auto` when both are configured and Henry Image should try the normal order

## Route contract

- `responses` requires `model`
- `images` requires `image-model`
- `auto` requires both

## Configuration priority

1. explicit CLI flags
2. canonical `HENRY_IMAGE_*` environment variables

There is no fallback to legacy names.
