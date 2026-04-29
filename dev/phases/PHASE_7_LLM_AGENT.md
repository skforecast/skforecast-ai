# Phase 7 — LLM Planner & Explainer

## Goal

Add a Pydantic AI agent that can: (a) parse natural-language user intent into a
`ForecastPlan`, (b) explain a deterministic recommendation in plain language,
(c) answer follow-up questions about results. The agent uses skills and
`llms-full.txt` as context.

## Files to Create

```
skforecast_ai/llm/prompts.py          (system prompts, skill loader)
skforecast_ai/llm/agent.py            (Pydantic AI agent definition + tools)
tests/test_llm_agent.py
```

## Agent Design

```python
from pydantic_ai import Agent

forecasting_agent = Agent(
    model,                              # from Phase 6
    output_type=ForecastPlan,           # structured output
    system_prompt=system_prompt,        # built from skills + llms-full.txt
    tools=[profile_data, recommend, generate_code],  # deterministic tools
    retries=2,
)
```

## Prompts (prompts.py)

| Function | Responsibility |
|----------|----------------|
| `load_skill(skill_name)` | Read SKILL.md + references from `skills/` folder |
| `load_llms_reference()` | Read `resources/llms-full.txt` |
| `build_system_prompt(skills, reference)` | Assemble system prompt with role, rules, context |
| `build_explain_prompt(plan, profile)` | Prompt for generating explanation of a recommendation |

## Agent Tools (registered via `@agent.tool`)

| Tool | What it does |
|------|-------------|
| `profile_data` | Calls `create_data_profile()` — gives the agent data awareness |
| `recommend` | Calls `recommend_plan()` — deterministic recommendation |
| `generate_code` | Calls `generate_code()` — produces script from plan |

The agent does NOT make forecasting decisions. It translates user intent to
tool calls and explains the deterministic outputs.

## Tests (tests/test_llm_agent.py)

Use `pydantic_ai.models.test.TestModel` for deterministic testing without
real API calls.

| Test | What it validates |
|------|-------------------|
| `test_agent_returns_forecast_plan` | Agent output conforms to `ForecastPlan` schema |
| `test_agent_calls_profile_tool` | Agent invokes `profile_data` tool on data question |
| `test_agent_calls_recommend_tool` | Agent invokes `recommend` tool |
| `test_system_prompt_includes_skills` | System prompt contains skill content |
| `test_system_prompt_includes_reference` | System prompt contains llms-full.txt content |
| `test_explain_prompt_uses_plan` | Explanation prompt includes plan details |

## Done Criteria

- [ ] Agent can be instantiated with any model from Phase 6
- [ ] Agent produces valid `ForecastPlan` via structured output
- [ ] System prompt is built from skills + `llms-full.txt` at runtime
- [ ] Agent tools delegate to deterministic functions (no LLM decision-making for forecasting logic)
- [ ] `pytest tests/test_llm_agent.py` passes using `TestModel` (≥ 6 tests)
