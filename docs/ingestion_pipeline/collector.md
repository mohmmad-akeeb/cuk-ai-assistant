# Phase A: Collector Deep-Dive

The collector is responsible for the asynchronous discovery and raw storage of assets.

## Key Components
- **Route Walker**: Crawls web pages based on defined routes.
- **Async Client**: Manages concurrent network requests.
- **Manifest Writer**: Keeps a record of crawled assets in `data/raw/manifest.jsonl`.
