# Implementation Phases — skforecast-ai

Detailed breakdown of the plan into incremental phases. Each phase is
self-contained: it produces testable code, has explicit "done" criteria, and
does not require any later phase to work.

Phases are ordered by dependency. Every phase builds only on what previous
phases delivered. Full details for each phase live in `dev/phases/`.

---

## Phases

| # | Phase | Detail file | Depends on | Tests |
|---|-------|-------------|-----------|-------|
| 1 | Package Skeleton & Schemas | [PHASE_1_PACKAGE_SKELETON.md](phases/PHASE_1_PACKAGE_SKELETON.md) | — | ≥ 6 |
| 2 | Data Profiler | [PHASE_2_DATA_PROFILER.md](phases/PHASE_2_DATA_PROFILER.md) | Phase 1 | ≥ 9 |
| 3 | Recommendation Engine | [PHASE_3_RECOMMENDATION.md](phases/PHASE_3_RECOMMENDATION.md) | Phases 1, 2 | ≥ 8 |
| 4 | Code Generation | [PHASE_4_CODE_GENERATION.md](phases/PHASE_4_CODE_GENERATION.md) | Phases 1–3 | ≥ 6 |
| 5 | CLI (Tier 0 complete) | [PHASE_5_CLI.md](phases/PHASE_5_CLI.md) | Phases 1–4 | ≥ 6 |
| 6 | LLM Provider Abstraction | [PHASE_6_LLM_PROVIDER.md](phases/PHASE_6_LLM_PROVIDER.md) | Phase 1 | ≥ 8 |
| 7 | LLM Agent & Explainer | [PHASE_7_LLM_AGENT.md](phases/PHASE_7_LLM_AGENT.md) | Phases 1–4, 6 | ≥ 6 |
| 8 | ForecastingAssistant API | [PHASE_8_ASSISTANT_API.md](phases/PHASE_8_ASSISTANT_API.md) | Phases 1–7 | ≥ 8 |
| 9 | Execution & Validation | [PHASE_9_EXECUTION.md](phases/PHASE_9_EXECUTION.md) | Phases 1–4, 8 | ≥ 6 |
| | | | **Total** | **≥ 63** |

---

## Dependency Graph

```
Phase 1 (Skeleton + Schemas)
├── Phase 2 (Data Profiler)
│   └── Phase 3 (Recommendation Engine)
│       └── Phase 4 (Code Generation)
│           └── Phase 5 (CLI — Tier 0 ✓)
├── Phase 6 (LLM Provider)
│   └── Phase 7 (LLM Agent)
│       └── Phase 8 (ForecastingAssistant — MVP ✓)
│           └── Phase 9 (Execution — Post-MVP)
```

Phases 2–5 and Phase 6 can be developed **in parallel** since they have no
mutual dependencies (they both depend only on Phase 1).

---

## Milestones

| Milestone | After phase | What the user can do |
|-----------|-------------|---------------------|
| **Tier 0 usable** | Phase 5 | `skforecast-ai inspect/recommend/generate-code` with no LLM |
| **MVP complete** | Phase 8 | Full Python API + CLI with optional LLM enhancement |
| **Execution ready** | Phase 9 | `assistant.run()` returns actual forecasts and metrics |
