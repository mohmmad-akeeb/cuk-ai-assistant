# Ingestion Collector

The collector subsystem is responsible for fetching raw data from the source systems and creating a manifest for downstream processing.

## Architectural Design
- Follows the Open/Closed Principle (OCP) by using interchangeable client adapters.
- Uses `DirectApiClient` for raw HTTP communication with the target school/department APIs.
- Employs `ManifestWriter` to track all fetched files and their provenance.
- Implements route walking via `RouteWalker` to discover the full hierarchy of data.

## Key Components
- `cuk_assistant/ingestion/collector/subsystems/client.py`: Provides `DirectApiClient` for fetching data from external endpoints.
- `cuk_assistant/ingestion/collector/subsystems/manifest.py`: Provides `ManifestWriter` and `ManifestEntry` for tracking.
- `cuk_assistant/ingestion/collector/subsystems/route_walker.py`: Implements logic for discovering endpoints/nodes.
- `cuk_assistant/ingestion/collector/runner.py`: Orchestrates the collection process, including PDF downloads and caching.
