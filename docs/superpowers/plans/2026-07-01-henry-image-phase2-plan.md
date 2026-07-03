# Henry Image Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `henry-image` 从“已经完成首轮拆分但主脚本仍然过重”的状态，推进到“真正的薄入口 + 可测试自检 + 有用但不惊扰用户的状态层”。

**Architecture:** 保持现有命令名、JSON envelope、auth/routing/job 行为兼容。继续沿用 `henry_image_core/` 方向，把 `henry_image.py` 收敛成解析与分发入口，把 provider/auth/self-check/command orchestration 下沉到小模块。状态层只应用安全默认值，不改动 secret、全局配置或 provider 选择优先级。

**Tech Stack:** Python 3、pytest、JSON/JSONL、现有 Codex/AiMaMi/OpenAI-compatible HTTP 路由、`henry-image/.cache` 本地状态文件。

---

## Current State Snapshot

- 已完成第一轮模块化：`henry_image_core/` 已存在，workflow metadata 与 workflow profile 已落地。
- 兼容性验证已通过：目标 pytest 集合 `37 passed`，`quick_validate` 通过。
- 主要剩余问题不在功能缺失，而在结构收口不彻底：
  - `scripts/henry_image.py` 仍然约 5500 行；
  - `workflow-profile` 目前主要是“记录并回显”，还没有形成稳定、可解释的软默认值层；
  - `quick_validate` 逻辑过大，维护成本高，回归定位慢；
  - provider/auth/routing 仍有部分核心决策留在主脚本。

## Phase Goal

本阶段只做三件事：

1. 让 `henry_image.py` 真正变成薄入口。
2. 让 workflow profile 从“被动记录”升级为“可控的软默认值”。
3. 让 `quick_validate` 变成可拆、可测、可维护的自检集合。

不做：

- provider 后端重写；
- 新增破坏性命令；
- 引入聊天里贴密钥的流程；
- 为了“像 niu-image-gen”而硬编码单后端。

### Task 1: Make The Entry Script Truly Thin

**Files:**
- Modify: `.\scripts\henry_image.py`
- Create: `.\scripts\henry_image_core\commands.py`
- Create: `.\scripts\henry_image_core\diagnostics.py`
- Test: `.\tests\test_p0_p1.py`

- [ ] Move `command_generate` / `command_edit` / `command_batch` into `henry_image_core.commands`.
- [ ] Move `command_probe` / `command_probe_image_providers` / `command_provider_cache` into `henry_image_core.diagnostics`.
- [ ] Move `command_job_status` / `command_job_diagnose` / `command_job_cancel` / `command_job_list` / `command_job_cleanup` into `henry_image_core.diagnostics` or `commands`, whichever keeps ownership clearer.
- [ ] Keep `henry_image.py` responsible only for constants, parser wiring, thin wrappers, and `main()` dispatch.
- [ ] Re-run the existing targeted pytest suite and `quick_validate`.

**Acceptance:**
- `henry_image.py` no longer owns the bulk of command orchestration.
- Existing command names and output envelopes stay unchanged.
- `quick_validate` and the current pytest suite remain green.

### Task 2: Finish Provider/Auth/Routing Extraction

**Files:**
- Modify: `.\scripts\henry_image.py`
- Modify: `.\scripts\henry_image_core\auth.py`
- Modify: `.\scripts\henry_image_core\providers.py`
- Modify: `.\scripts\henry_image_core\routing.py`
- Test: `.\tests\test_p0_p1.py`
- Test: `.\tests\test_p1_6_adaptive_auth.py`

- [ ] Move `auth_profiles`, `auth_candidates`, and related auth summary/dedupe shaping fully into `henry_image_core.auth`.
- [ ] Move image provider discovery, health filtering, and candidate notes fully into `henry_image_core.providers`.
- [ ] Move `policy_base_url_candidates` and candidate fallback decisions into `henry_image_core.routing`.
- [ ] Keep any necessary compatibility wrappers in `henry_image.py` only if tests still import those names directly.
- [ ] Add or extend tests for provider ordering, dedicated env precedence, strict/all/auto policy, and health-based candidate skipping.

**Acceptance:**
- Main script no longer owns the key provider/auth/routing decision algorithms.
- Dedicated-provider precedence and dynamic provider discovery remain unchanged.
- Adaptive auth tests and candidate-policy tests stay green.

### Task 3: Turn Workflow Profile Into Soft Defaults

**Files:**
- Modify: `.\scripts\henry_image_core\workflow.py`
- Modify: `.\scripts\henry_image.py`
- Test: `.\tests\test_workflow_profile.py`

- [ ] Add a `resolve_workflow_defaults(...)` helper that reads `workflow-profile.json` before command execution.
- [ ] Apply profile values only when the incoming args are still on tool defaults; explicit CLI flags, explicit env overrides, and dedicated provider settings must win.
- [ ] Start with safe fields only: `size`, `quality`, `output_format`, and `route`.
- [ ] Defer automatic output-path rewriting unless a separate design explicitly approves it.
- [ ] Emit metadata describing whether profile defaults were applied, so behavior is visible and debuggable.
- [ ] Add tests covering three cases: no profile, profile applied, explicit CLI override wins.

**Acceptance:**
- Workflow profile improves continuation behavior without surprising first-use behavior.
- No secret data enters the profile.
- Tests prove precedence rules.

### Task 4: Break Quick Validate Into Testable Self-Check Groups

**Files:**
- Modify: `.\scripts\henry_image.py`
- Modify: `.\scripts\henry_image_core\diagnostics.py`
- Test: `.\tests\test_p0_p1.py`

- [ ] Split `quick_validate` into focused helpers such as:
  - docs/reference contract checks
  - auth adaptation checks
  - provider discovery checks
  - workflow metadata checks
  - job diagnosis checks
- [ ] Keep the CLI-facing `quick_validate` command and output schema unchanged.
- [ ] Add direct tests for the extracted helpers where possible, so future regressions do not require whole-command debugging.
- [ ] Preserve the new dedicated-env isolation behavior.

**Acceptance:**
- `quick_validate` is still one command to the user, but internally it is composed of small checks.
- Regressions can be traced to one self-check group instead of one giant block.

### Task 5: Tighten Contract Coverage Around Workflow And Recovery

**Files:**
- Modify: `.\tests\test_workflow_profile.py`
- Modify: `.\tests\test_p1_5_diagnostics_cancel.py`
- Modify: `.\tests\test_p0_p1.py`

- [ ] Add workflow metadata assertions for `edit`, `batch`, `job-status`, and `job-diagnose`.
- [ ] Add failure-path assertions for `stage`, `replay_command`, and `next_action`.
- [ ] Add a regression test that confirms recovery-oriented results still carry `workflow_profile`.
- [ ] Keep test count focused; do not add redundant snapshots for every envelope field.

**Acceptance:**
- Workflow metadata is treated as contract, not incidental output.
- Recovery paths are covered as well as happy paths.

### Task 6: Final Documentation And Developer Maintenance Pass

**Files:**
- Modify: `.\SKILL.md`
- Modify: `.\references\quick-card.md`
- Modify: `.\references\routing.md`
- Create: `.\references\developer-map.md`

- [ ] Keep `SKILL.md` user-first; do not move internal maintenance detail into the main workflow page.
- [ ] Add `developer-map.md` documenting module ownership and where to change routing/auth/workflow/job logic.
- [ ] Tighten `quick-card.md` around replay/recovery and the workflow metadata fields users now see.
- [ ] Remove or trim any duplicated deep-dive text that no longer adds value after the workflow-first rewrite.

**Acceptance:**
- User docs stay short and execution-first.
- Developer maintenance information has a home outside the main skill entry page.

## Execution Order

1. Task 1
2. Task 2
3. Re-run full targeted verification
4. Task 3
5. Task 4
6. Task 5
7. Task 6
8. Re-run full targeted verification and `quick_validate`

## Verification Gate

Minimum verification for this phase:

- `python -m pytest -q .\tests\test_p0_p1.py .\tests\test_p1_5_diagnostics_cancel.py .\tests\test_p1_6_adaptive_auth.py .\tests\test_workflow_profile.py`
- `python .\scripts\henry_image.py quick_validate`

## Stop Conditions

This phase is complete when:

- `henry_image.py` is demonstrably thin enough to read as an entrypoint;
- workflow profile has clear, tested soft-default behavior;
- `quick_validate` is split into maintainable internal checks;
- the existing external CLI contract still holds.
