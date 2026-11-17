# Evaluation Framework Documentation

## Evaluation Strategy
The CUK RAG Chatbot employs a robust evaluation framework for RAG quality assurance, located in `cuk_assistant/evals/`.

- **Framework**:
  - Evaluation is based on metrics like faithfulness, relevancy, and citation accuracy.
  - The framework must be integrated into the CI/CD pipeline to ensure that model updates or ingestion changes do not degrade performance.

- **Implementation**:
  - `cuk_assistant/evals/evaluator.py` provides the logic for running evaluations.
  - Evaluation data is processed and stored for analysis (e.g., in `reports/`).

For custom evaluation routines, ensure compliance with the existing Pydantic models in `cuk_assistant/evals/schemas.py`.
