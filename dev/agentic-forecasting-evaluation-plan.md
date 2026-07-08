# Plan: Deepening the Agentic Experience in skforecast-ai Docs

## 1. Expert Reasoning & Evaluation (The Disconnect)

The recent updates to the high-level documentation (`README.md` and `how-it-works-and-trust.md`) successfully establish the core pitch: `skforecast-ai` is a **Guardrailed Agentic System** that pairs a deterministic Execution Engine with an LLM Reasoning Engine. This is an excellent architecture for enterprise data science because it solves the LLM hallucination problem.

However, moving deeper into the actual user guides, **the documentation falls short of delivering an "agentic" feel.**

Here are the three primary disconnects:
1.  **The Quickstart Paradox:** In `first-forecast.md`, the user builds their very first model and prints the results... but they never interact with the AI! To a new user, this looks like standard Auto-ML (e.g., AutoGluon), not an agentic co-pilot. The user's "Aha!" moment should be seeing the agent analyze the forecast it just made.
2.  **The Siloed AI:** Currently, the LLM is isolated almost entirely within `using-the-ai-assistant.md`. If `skforecast-ai` is truly an agentic co-pilot, the agent should be helping the user at *every* step of the workflow. Treating the LLM as an isolated feature rather than an integrated companion diminishes the agentic identity.
3.  **Human-in-the-Loop Loop:** Users currently read the workflow as a straight line (`profile -> plan -> execute`). The interactive "Agentic Loop" (Execute -> Agent Evaluates -> Agent Suggests Refinements -> Human Approves) needs to be explicitly shown in practice, not just in diagrams.

## 2. Implementation Plan

To fully realize the "Agentic Forecasting" identity, we must de-silo the LLM and weave it throughout the user's journey.

### Step 1: Fix the "Quickstart Paradox" (`first-forecast.md`)
*   **Action:** Add a "Step 5: Ask the Agent to Explain" section.
*   **Content:** After printing the metrics, add a small code snippet showing the user passing the `result` to the `assistant.ask()` method. 
*   **Why:** This guarantees the user's first impression includes the LLM Reasoning Engine analyzing the deterministic output.

### Step 2: De-silo the AI across the User Guides
Instead of isolating the LLM in one file, we will add "Agentic Pro-Tips" across the other guides:
*   **`understanding-your-data.md`:** Add a snippet showing how to pass the `profile` to `ask()` if the user is confused by detected anomalies (e.g., missing frequencies).
*   **`customizing-the-model.md`:** Show how the user can ask the LLM for hyperparameter tuning recommendations for a specific forecaster *before* calling `refine_plan()`.
*   **`troubleshooting.md`:** Explicitly show how to pass a `ForecastExecutionError` back to the assistant so it can cross-reference its Troubleshooting Skills and suggest a fix.

### Step 3: Formalize the Human-in-the-loop workflow (`the-forecasting-workflow.md`)
*   **Action:** Explicitly write out the "Agentic Loop" in the text, accompanying the newly updated Mermaid diagram.
*   **Content:** Describe the workflow as iterative: The Execution Engine runs -> The Reasoning Engine evaluates the `BacktestResult` -> The Reasoning Engine suggests changes -> The User applies them via `refine_plan`.