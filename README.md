# Henry Image Skill

Henry Image is a Codex skill for Henry's image-generation workflow. It keeps the operational instructions, local CLI helper, and regression tests in one small project.

## Structure

- `SKILL.md` - skill entrypoint and routing rules.
- `references/` - workflow notes, setup, routing, prompt compilation, review, and failure handling.
- `scripts/henry_image.py` - CLI entrypoint.
- `scripts/henry_image_core/` - CLI support modules.
- `tests/` - pytest coverage for routing, auth, diagnostics, and workflow metadata.
- `agents/` - local agent configuration.

## Local Checks

Run the test suite from this directory:

```powershell
python -m pytest
```

Generated caches, output images, logs, and local environment files are intentionally ignored by git.
