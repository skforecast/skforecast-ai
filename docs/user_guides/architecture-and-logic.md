# Architecture & Logic

**skforecast-ai** is built on a unique architectural philosophy that completely separates *execution* from *reasoning*. This design ensures that all forecasting results are 100% deterministic, testable, and reproducible, while simultaneously leveraging the conversational and explanatory power of Large Language Models (LLMs) to guide the user.

This guide exhaustively details the internal structure, the state transformations within the forecasting pipeline, and the "Knowledge as Code" pattern that grounds the LLM.

---

## 1. High-Level Architecture

At its core, `skforecast-ai` operates as a rigid, rule-based inference engine. The LLM does not write code blindly; instead, it acts strictly as an *observer* and *explainer* of the deterministic pipeline.

```mermaid
flowchart TD
    %% Styling
    classDef data fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#000
    classDef core fill:#f3e5f5,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef llm fill:#fff3e0,stroke:#6a1b9a,stroke-width:2px,stroke-dasharray: 5 5,color:#000
    classDef output fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#000

    A[(User Dataset)]:::data --> B(ForecastingAssistant):::core
    
    subgraph Deterministic Core
        direction TB
        B --> C[1. Profiling]:::core
        C --> D[2. Recommendation]:::core
        D --> E[3. Rendering]:::core
        E --> F[4. Execution]:::core
    end
    
    subgraph LLM Overlay
        direction TB
        CTX[Agent Context]:::llm
        RAG[SKILL.md RAG]:::llm
        EXP[Explanations]:::llm
    end

    %% Interactions
    C -. State/Decisions .-> CTX
    D -. State/Decisions .-> CTX
    CTX <--> RAG
    CTX --> EXP
    B -.->|ask API| CTX
    
    F ==> G[(Predictions & Metrics)]:::output
    F ==> H[(Rendered Python Script)]:::output
```

### Modes of Operation
*   **Deterministic Mode (Default):** Runs the pipeline from profiling to execution. It generates deterministic `skforecast` code and predictions without requiring an internet connection or an API key.
*   **LLM Mode:** Activated when an LLM provider (e.g., `openai:gpt-4o`) is configured. The assistant reads the internal pipeline state (e.g., understanding *why* an `LGBMRegressor` was chosen over `Ridge`) and communicates this to the user via the `.ask()` interface.

---

## 2. The Forecasting Pipeline

The deterministic core follows a strictly functional pipeline design. Data flows sequentially through discrete stages, with each stage applying pure functions to transform an immutable `pydantic` schema into the next.

```mermaid
flowchart LR
    %% Styling
    classDef schema fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef data fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#000

    A[(Raw Data)]:::data -->|1. profile| B{DataProfile}:::schema
    B -->|2. plan| C{ForecastPlan}:::schema
    C -->|3. render| D{RenderedScript}:::schema
    D -->|4. execute| E[(ForecastResult)]:::schema
```

### Stage 1: Profiling (`skforecast_ai.profiling`)

The pipeline begins by inspecting the raw user dataset. This stage acts as a robust data validator and metadata extractor. It **does not** fit any models or analyze statistical target relationships; its sole purpose is to understand the structural limitations of the input data.

```mermaid
flowchart TD
    classDef schema fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef func fill:#eceff1,stroke:#607d8b,stroke-width:1px,color:#000
    classDef data fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#000

    A[(Raw Data)]:::data --> B[create_data_profile]:::func
    
    subgraph Internal Operations
        direction TB
        B --> C1(_coerce_to_dataframe):::func
        B --> C2(infer_frequency):::func
        B --> C3(check_nans):::func
        B --> C4(identify_series):::func
    end
    
    C1 & C2 & C3 & C4 --> D{DataProfile Schema}:::schema
```

**Key Operations:**
- **Index Analysis:** Detects the frequency (e.g., daily, monthly) and validates if the index is monotonic and complete.
- **Missing Values Tracking:** Precisely locates `NaN` values. The presence of NaNs heavily dictates which downstream preprocessing steps or machine learning estimators are viable.
- **Output:** A strongly typed `DataProfile` object. This schema acts as the immutable ground truth about the dataset for the rest of the pipeline.

### Stage 2: Recommendation (`skforecast_ai.recommendation`)

This is the "Brain" of the deterministic engine. Using a series of hardcoded, sequential business rules, it evaluates the `DataProfile` to determine the optimal forecasting architecture. This transparent heuristic approach intentionally avoids the "black box" nature of traditional AutoML.

```mermaid
flowchart TD
    classDef schema fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef func fill:#eceff1,stroke:#607d8b,stroke-width:1px,color:#000

    A{DataProfile Schema}:::schema --> B[Recommendation Engine]:::func
    
    subgraph Rule-Based Heuristics
        direction TB
        B --> C1(select_task_type_from_forecaster):::func
        C1 --> C2(select_forecaster_and_candidates):::func
        C2 --> C3(select_estimator_and_candidates):::func
        C3 --> C4(derive_preprocessing_steps):::func
        C4 --> C5(select_lags_and_window_features):::func
    end
    
    C5 --> D{ForecastPlan Schema}:::schema
```

**Key Operations:**
- **Task Resolution:** Identifies if the problem requires a `single_series`, `multi_series`, `multivariate`, or `foundation` architecture.
- **Forecaster & Estimator Selection:** Determines the core modeling classes. For example, it defaults to `Ridge` for small datasets (<250 observations) to prevent overfitting, transitioning to `LGBMRegressor` for larger datasets.
- **Hyperparameter Derivation:** Calculates safe default parameters (like the number of lags based on the inferred frequency) and injects necessary data transformers (e.g., missing value imputers or standard scalers) to ensure the generated model can compile safely.
- **Output:** A `ForecastPlan` object. This is a comprehensive, declarative blueprint detailing exactly *how* the forecast will be executed, independently of any actual Python code.

### Stage 3: Rendering (`skforecast_ai.rendering`)

The rendering engine acts as a dynamic code generator. It translates the abstract `ForecastPlan` into a concrete, human-readable Python script, ensuring the user can audit, modify, or independently deploy the code.

```mermaid
flowchart TD
    classDef schema fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef func fill:#eceff1,stroke:#607d8b,stroke-width:1px,color:#000

    A{ForecastPlan Schema}:::schema & B{DataProfile Schema}:::schema --> C[_RENDER_DISPATCH]:::func
    
    subgraph Code Assembly
        direction TB
        C --> D1(_emit_imports):::func
        C --> D2(_emit_data_loading):::func
        C --> D3(_emit_index_setup):::func
        C --> D4(_emit_preprocessing_steps):::func
        C --> D5(_emit_forecaster_creation):::func
        C --> D6(_emit_fit_and_predict):::func
    end
    
    D1 & D2 & D3 & D4 & D5 & D6 --> E{RenderedScript Schema}:::schema
```

**Key Operations:**
- **Code Assembly:** Dynamically builds the script line-by-line via specialized helper functions. It handles the injection of `pandas` index validation logic and complex `skforecast` pipeline instantiation.
- **Formatting:** Applies rigorous string formatting rules (e.g., `_emit_aligned_kwargs`) so the generated script is not just executable, but highly idiomatic and visually structured.
- **Output:** A `RenderedScript` object containing valid Python code, logically split into sections (`imports`, `data_loading`, `core_logic`).

### Stage 4: Execution (`skforecast_ai.execution`)

To guarantee absolute fidelity—meaning the code shown to the user is *exactly* the code generating the results—`skforecast-ai` dynamically compiles and executes the `RenderedScript` using Python's native `exec()` function within an isolated programmatic namespace.

```mermaid
flowchart TD
    classDef schema fill:#fff9c4,stroke:#f57f17,stroke-width:2px,color:#000
    classDef func fill:#eceff1,stroke:#607d8b,stroke-width:1px,color:#000
    classDef data fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#000

    A{RenderedScript Schema}:::schema & B[(Raw Data)]:::data --> C[run_forecast / run_backtest]:::func
    
    subgraph Native Isolation
        direction TB
        C --> D1[namespace = data: user_df]:::func
        D1 --> D2[exec core_logic, namespace]:::func
        D2 --> D3[extract predictions]:::func
        D2 --> D4[extract metrics_df]:::func
    end
    
    D3 & D4 --> E[(ForecastResult)]:::schema
```

**Key Operations:**
- **Environment Setup:** Loads the user's actual `pandas.DataFrame` directly into the dictionary namespace (`namespace = {"data": data}`). This avoids expensive disk I/O (like writing temporary CSVs) during execution.
- **State Extraction:** Following execution, the runner safely extracts the newly instantiated model (`forecaster`), the generated predictions DataFrame, and calculated performance metrics (like MAE or RMSE) back out of the namespace.
- **Output:** A standard dictionary containing the final `pandas` objects and the raw executed code, ready for downstream use or user inspection.

---

## 3. "Knowledge as Code" (Skills)

A critical challenge in AI assistants is keeping the LLM's knowledge synchronized with the codebase's logic. If the recommendation engine dictates one rule, but the LLM explains another based on outdated pre-training data, user trust is destroyed.

`skforecast-ai` solves this utilizing the **Knowledge as Code** pattern. Business rules and heuristic thresholds are extracted into isolated Markdown files called **Skills** (located in `skforecast_ai/skills/`).

```mermaid
flowchart TD
    classDef doc fill:#e3f2fd,stroke:#0288d1,stroke-width:2px,color:#000
    classDef target fill:#f5f5f5,stroke:#424242,stroke-width:2px,color:#000

    A([📄 SKILL.md]):::doc -->|Acts as Documentation| B(Human Readable / Developers):::target
    A -->|Injected via .ask| C(RAG Context / LLM Agent):::target
    A -->|Hardcoded Heuristics| D(Mirrored Logic / Recommendation Engine):::target
```

**Architectural Benefits:**
1. **Single Source of Truth:** When the core team adopts a new forecasting best practice, they update the `SKILL.md` file. The documentation and the LLM context update instantly.
2. **Contextual Grounding:** When the user asks the LLM a question (e.g., *"Why did you choose Ridge instead of XGBoost?"*), the agent reads the relevant skill file to ground its answer in `skforecast`'s actual architectural rules, eliminating AI hallucinations.
3. **Total Transparency:** Users can browse the `skforecast_ai/skills/` directory on GitHub to understand exactly the rules the assistant is bound by.