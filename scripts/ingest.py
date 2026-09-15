"""CLI to build (or rebuild) the Milvus vector index from `data/`.

Usage:
    python -m scripts.ingest                 # rebuild from scratch (default)
    python -m scripts.ingest --append        # add to the existing collection
    python -m scripts.ingest --data-dir data # override data directory
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.logging_config import configure_logging, get_logger
from app.rag.ingestion import ingest

logger = get_logger("ingest")


def main() -> int:
    configure_logging()
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Ingest company documents into Milvus.")
    parser.add_argument("--data-dir", default=settings.data_dir, help="Path to the data directory.")
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to the existing collection instead of rebuilding it.",
    )
    args = parser.parse_args()

    if not settings.azure_openai_configured:
        logger.error("azure_openai_not_configured", hint="Set AZURE_OPENAI_* in your .env")
        return 2

    try:
        count = ingest(data_dir=args.data_dir, rebuild=not args.append)
    except Exception as exc:  # noqa: BLE001
        logger.error("ingestion_failed", error=str(exc))
        return 1

    logger.info("ingest_done", chunks_indexed=count, collection=settings.milvus_collection)
    return 0 if count > 0 else 3


if __name__ == "__main__":
    sys.exit(main())
