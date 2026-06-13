# Plan: Evaluating and Enhancing the Agentic Forecasting Presentation

## Objective
Evaluate and update the `skforecast-ai` documentation to emphasize the "agentic" nature of the tool. The goal is to shift the perception from a simple "code generator with an LLM wrapper" to a **powerful Agentic Forecasting Assistant**. 

The core message must be: `skforecast-ai` boosts the forecasting experience and accelerates workflows by combining the robust, production-ready, and deterministic execution engine of `skforecast` with the reasoning, exploratory, and explanatory potential of Large Language Models.

## Core Messaging Strategy
Currently, the documentation heavily emphasizes what the LLM *cannot* do (e.g., "it never changes the math"). While this is crucial for trust, it undersells the agentic experience. We need to reframe this:
*   **Current Frame:** "Deterministic pipeline with an optional LLM overlay."
*   **New Frame:** "An Agentic Assistant that pairs reasoning (LLM) with guaranteed execution (Deterministic Engine)."

The assistant acts as a Senior Data Scientist: it inspects the data, formulates a strategy based on established best practices (Skills), executes the strategy flawlessly, and then explains its findings to you.

## Areas for Evaluation and Update

### 1. Root `README.md` and `docs/README.md` (The Hook)
*   **Current:** Focuses heavily on "Deterministic by design" and "Runs locally, no API key".
*   **Agentic Update:** Introduce the concept of the **"Agentic Workflow"**. 
    *   Highlight that the assistant *automates the cognitive load* of data profiling, model selection, and pipeline construction.
    *   Use terminology like "Pair-programming for Time Series" or "Your Expert Forecasting Co-pilot".
    *   Ensure the tagline clearly states the synergy: *Leveraging the reasoning potential of LLMs alongside the robust forecasting engine of skforecast.*

### 2. User Guide: `how-it-works-and-trust.md`
*   **Current:** Explains the strict separation of concerns to build trust.
*   **Agentic Update:** Rebrand the two modes to highlight their synergy.
    *   Explain the architecture as a **"Guardrailed Agentic System"**.
    *   The LLM is the "Reasoning Engine" (reads profiles, evaluates metrics, suggests improvements via `ask()`).
    *   The Python core is the "Execution Engine" (guarantees reproducibility, avoids hallucinations).
    *   This is the ideal agent architecture for enterprise data science: autonomous reasoning combined with strict, auditable execution.

### 3. User Guide: `the-forecasting-workflow.md`
*   **Current:** A linear pipeline of `profile -> plan -> execute`.
*   **Agentic Update:** Present the workflow as an interactive, agentic loop.
    *   Show how a user interacts with the assistant: The assistant proposes a plan, the user refines it, the assistant executes it, and the user asks the assistant to interpret the results.
    *   Emphasize that the assistant is applying "Knowledge as Code" (Skills) autonomously during the profiling and planning phases.

### 4. User Guide: `using-the-ai-assistant.md`
*   **Current:** Treats the LLM as an optional Q&A add-on.
*   **Agentic Update:** Elevate this section. Show advanced agentic use cases.
    *   Highlight how the assistant can diagnose execution errors (Troubleshooting).
    *   Demonstrate how it evaluates Backtesting metrics and suggests concrete modeling improvements (like changing lags or adding calendar features).
    *   Showcase the assistant as an active participant in improving forecast accuracy, not just a documentation reader.

## Action Items
1.  **Drafting:** Rewrite the introductory paragraphs of the README files to incorporate the "Agentic Assistant" framing.
2.  **Reviewing `ask()` capabilities:** Ensure the documentation heavily features the `ask()` method's ability to act as an agent (e.g., passing `backtest_result` to get strategic recommendations).
3.  **Visuals:** Consider updating the Mermaid diagrams in the architecture docs to show a "Feedback Loop" where the user uses the LLM to refine the deterministic plan, visually representing the agentic workflow.