# Phase 8 — ForecastingAssistant (Public API)

## Goal

Create the unified `ForecastingAssistant` class that ties together all
components and provides the user-facing Python API described in the plan.

## Files to Create

```
skforecast_ai/assistant.py         (ForecastingAssistant class)
tests/test_assistant.py
```

## Public API

```python
from skforecast_ai import ForecastingAssistant

# Tier 0
assistant = ForecastingAssistant(llm=None)
result = assistant.inspect(data=df, target="sales", date_column="date")
result = assistant.recommend(data=df, target="sales", date_column="date", horizon=30)
result = assistant.generate_code(data=df, target="sales", date_column="date", horizon=30)

# Tier 1/2
assistant = ForecastingAssistant(llm="openai:gpt-4o-mini", send_data_to_llm=False)
result = assistant.ask("I have daily sales for 3 stores, forecast 30 days ahead", data=df)
result = assistant.explain(plan=result.plan)
```

## Class Design

```python
class ForecastingAssistant:
    def __init__(
        self,
        llm: str | None = None,
        base_url: str | None = None,
        send_data_to_llm: bool = False,
    ): ...

    def inspect(self, data, target, date_column=None, series_id_column=None) -> DataProfile: ...
    def recommend(self, data, target, date_column=None, horizon=1, **kwargs) -> RecommendResult: ...
    def generate_code(self, data, target, date_column=None, horizon=1, **kwargs) -> GenerateResult: ...
    def ask(self, question: str, data=None, **kwargs) -> AskResult: ...   # requires llm
    def explain(self, plan: ForecastPlan) -> str: ...                     # requires llm
```

## Result Schemas (add to schemas.py)

```python
class RecommendResult(BaseModel):
    profile: DataProfile
    plan: ForecastPlan

class GenerateResult(BaseModel):
    profile: DataProfile
    plan: ForecastPlan
    code: str

class AskResult(BaseModel):
    profile: DataProfile | None
    plan: ForecastPlan | None
    code: str | None
    explanation: str
```

## Behavior Matrix

| Method | Tier 0 (llm=None) | Tier 1/2 (llm set) |
|--------|-------------------|---------------------|
| `inspect` | Deterministic profiling | Same |
| `recommend` | Deterministic rules | Rules + LLM explanation |
| `generate_code` | Deterministic | Same + LLM docstrings/comments |
| `ask` | Raises `LLMRequiredError` | LLM parses intent → tools |
| `explain` | Raises `LLMRequiredError` | LLM explains plan |

## Tests (tests/test_assistant.py)

| Test | What it validates |
|------|-------------------|
| `test_tier0_inspect` | Works without LLM |
| `test_tier0_recommend` | Returns RecommendResult without LLM |
| `test_tier0_generate_code` | Returns GenerateResult without LLM |
| `test_tier0_ask_raises` | `ask()` raises `LLMRequiredError` when `llm=None` |
| `test_tier0_explain_raises` | `explain()` raises `LLMRequiredError` when `llm=None` |
| `test_send_data_to_llm_default_false` | Default is `False` |
| `test_assistant_with_llm_recommend` | With mocked LLM, `recommend` returns enriched result |
| `test_assistant_accept_csv_path` | Accepts string path to CSV |
| `test_assistant_accept_dataframe` | Accepts pandas DataFrame |

## Done Criteria

- [ ] `from skforecast_ai import ForecastingAssistant` works
- [ ] Tier 0 methods work end-to-end without any LLM dependency
- [ ] Tier 1/2 methods work with `TestModel`
- [ ] `send_data_to_llm` flag is respected
- [ ] `LLMRequiredError` is raised for LLM-only methods when `llm=None`
- [ ] CLI updated to use `ForecastingAssistant` internally
- [ ] `pytest tests/test_assistant.py` passes (≥ 8 tests)
