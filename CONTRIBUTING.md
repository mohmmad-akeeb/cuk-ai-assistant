# Contributing to CUK RAG Chatbot

Thank you for contributing to the CUK RAG Chatbot! Please adhere to the following guidelines.

## 1. Architectural Invariants (Strict)
Every contribution must adhere to `GEMINI.md`, specifically:
- **Separation of Concerns (SoC)**
- **Dependency Injection (DI) via Protocols**
- **Open/Closed Principle (OCP)**

Failure to comply with these will lead to PR rejection.

## 2. Development Workflow
1. **Explore**: Use `tokenade` for exploring code (`skeleton`, `query`).
2. **Implement**: Keep changes minimal. Follow DI/OCP principles.
3. **Verify**: Run `ruff check` and relevant `pytest` suites before submitting.
4. **Logfire**: Ensure your changes include structured logging if they touch workflows or API endpoints.

## 3. Pull Requests
- PRs must be linked to a specific issue/feature.
- Ensure all tests pass.
- Maintain adherence to `GEMINI.md`.

## 4. Documentation
- Update `docs/` as necessary when changing the architecture or ingestion pipeline.
- New adapters must be registered correctly as per `registry.py`.
