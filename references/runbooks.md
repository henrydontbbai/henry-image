# Henry Image Runbooks

Reusable workflows for high-frequency Henry image tasks. Prefer `--background-job` for complex prompts and local `outputs`.

## character-board

1. Compile: character identity, poses, expressions, outfits, props, layout grid, negative constraints.
2. Run:
   ```powershell
   python $script generate --route auto --candidate-policy auto --background-job --timeout 900 --retries 1 --prompt-file character-board.txt --out output\imagegen\character-board.png --force
   ```
3. Poll with `job-status --job <job> --watch --interval 5`.
4. Review: identity consistency, pose count, hands/face, labels/text, layout completeness.
5. Retry only with targeted corrections; keep previous output as reference if identity drift matters.

## thumbnail-board

1. Define topic, audience, visual hook, 6-12 thumbnail slots, color direction, text/no-text rule.
2. Use `generate --background-job` for a board, or `batch --background-job` for separate files.
3. Review each slot for readability at small size and avoid random text unless explicitly requested.
4. Promote winners into focused single-image generations.

## ecommerce image set

1. Split tasks: hero, detail, lifestyle, scale/context, transparent-cutout.
2. Use `batch --result-jsonl output/imagegen/batch/results.jsonl --resume --skip-existing`.
3. Keep product geometry and materials in every task prompt.
4. Review for invented logos, incorrect text, warped product shape, and background suitability.

## complex poster

1. Separate image content from typography. Use raster for background/concept; use SVG/PDF/HTML for exact final text when needed.
2. Use `--background-job --timeout 900`.
3. If generated text is important and fails twice, stop raster iteration and build deterministic text layout.

## image-to-image variation

1. Classify input role: edit target, style reference, visual reference, or previous output.
2. Use `edit --image <path>` for local/reference images.
3. State what must stay unchanged and what may change.
4. If identity or product shape drifts, retry with stronger preservation language or lower-scope edit.

## local edit / mask

1. Use mask only when the editable area is clear.
2. Prefer `--route responses` for file-id workflows and `--route images` for OpenAI-compatible `/images/edits`.
3. Review that non-masked regions remain unchanged.

## batch variants

1. Store tasks in JSONL with explicit `out` paths.
2. Run dry-run first:
   ```powershell
   python $script batch --dry-run --input tasks.jsonl --result-jsonl output\imagegen\batch\results.jsonl
   ```
3. Run real batch with `--resume --skip-existing --max-images <n>`.
4. If interrupted, rerun with the same `--result-jsonl` and `--resume`.
5. Use result JSONL as the acceptance and retry ledger.
