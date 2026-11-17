# Deployment Documentation

## Overview
This document outlines the deployment strategy for the CUK RAG Chatbot, emphasizing our architectural invariants (SoC, DI, OCP).

## Containerization
The application is containerized using Docker to ensure environment consistency. The `Dockerfile` and `docker-compose.yml` are located in the project root.

- **Dependencies**: Managed via `uv` (as per project structure).
- **Architecture**:
  - The application is designed for modularity, allowing different vector stores or LLM providers to be injected via `core/factory.py`.
  - Deployment must NOT violate the OCP: adding a new adapter should require zero modifications to existing pipeline code.

## Environment Variables
The application requires several environment variables for configuration. See `.env.example` for the required keys.
*Crucial*: Never commit actual secrets or `.env` files.

## CI/CD Pipeline
- Automated testing is performed on every push to the main branch.

- Deployment environments must enforce structured logging and tracing for observability.

---

## Related Documentation
- [System Requirements](../requirements.md)
- [System Architecture](../architecture.md)
- [Observability](observability.md)
