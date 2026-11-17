"""cuk_assistant/ingestion/collector package.

Pure raw network collector (Extract & Load) writing to data/raw/.
"""

from cuk_assistant.ingestion.collector.subsystems.client import (
    API_BASE,
    DirectApiClient,
    download_pdf_cached,
)
from cuk_assistant.ingestion.collector.subsystems.manifest import ManifestEntry, ManifestWriter
from cuk_assistant.ingestion.collector.subsystems.route_walker import (
    SiteNode,
    build_node_table,
    fetch_all_nodes,
    nodes_to_jsonl,
)
from cuk_assistant.ingestion.collector.runner import run

__all__ = [
    "API_BASE",
    "DirectApiClient",
    "ManifestEntry",
    "ManifestWriter",
    "SiteNode",
    "build_node_table",
    "download_pdf_cached",
    "fetch_all_nodes",
    "nodes_to_jsonl",
    "run",
]
