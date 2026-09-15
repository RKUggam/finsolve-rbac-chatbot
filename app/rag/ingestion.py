"""Document ingestion: load `data/`, chunk, tag with department metadata, embed.

Directory layout drives access control: every file under `data/<department>/`
is tagged with that department, which the RBAC retriever later filters on. The
HR CSV is expanded into one document per employee so row-level facts stay intact
through chunking.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.logging_config import get_logger
from app.rbac.policy import Department
from app.rag.vectorstore import get_vector_store

logger = get_logger(__name__)

# Folders that are not one of our known departments are skipped with a warning.
_KNOWN_DEPARTMENTS = {d.value for d in Department}


def _title_from_path(path: Path) -> str:
    """Human-readable document title from a file name."""
    return path.stem.replace("_", " ").replace("-", " ").strip().title()


def _load_markdown(path: Path, department: str) -> list[Document]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return []
    return [
        Document(
            page_content=text,
            metadata={
                "department": department,
                "source": path.name,
                "title": _title_from_path(path),
                "doc_type": "markdown",
            },
        )
    ]


def _load_csv(path: Path, department: str) -> list[Document]:
    """Turn each CSV row into a compact 'key: value' document."""
    df = pd.read_csv(path)
    docs: list[Document] = []
    for idx, row in df.iterrows():
        lines = [f"{col}: {row[col]}" for col in df.columns if pd.notna(row[col])]
        content = f"HR employee record from {path.name}\n" + "\n".join(lines)
        docs.append(
            Document(
                page_content=content,
                metadata={
                    "department": department,
                    "source": path.name,
                    "title": _title_from_path(path),
                    "doc_type": "csv_row",
                    "row": int(idx),
                },
            )
        )
    return docs


def load_documents(data_dir: str | Path) -> list[Document]:
    """Load every supported file under `data/` into tagged Documents."""
    root = Path(data_dir)
    if not root.exists():
        raise FileNotFoundError(f"Data directory not found: {root.resolve()}")

    documents: list[Document] = []
    for dept_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        department = dept_dir.name.lower()
        if department not in _KNOWN_DEPARTMENTS:
            logger.warning("skipping_unknown_department_folder", folder=department)
            continue
        for file_path in sorted(dept_dir.rglob("*")):
            if not file_path.is_file():
                continue
            suffix = file_path.suffix.lower()
            if suffix in {".md", ".markdown", ".txt"}:
                documents.extend(_load_markdown(file_path, department))
            elif suffix == ".csv":
                documents.extend(_load_csv(file_path, department))
            else:
                logger.warning("skipping_unsupported_file", file=str(file_path))
    logger.info("documents_loaded", count=len(documents))
    return documents


def chunk_documents(documents: list[Document]) -> list[Document]:
    """Split documents into overlapping chunks, preserving metadata."""
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    chunks = splitter.split_documents(documents)
    logger.info("documents_chunked", chunks=len(chunks))
    return chunks


def ingest(data_dir: str | Path | None = None, rebuild: bool = True) -> int:
    """Full ingestion run. Returns the number of chunks indexed.

    `rebuild=True` drops and recreates the collection so re-runs are idempotent.
    """
    settings = get_settings()
    data_dir = data_dir or settings.data_dir
    documents = load_documents(data_dir)
    if not documents:
        logger.warning("no_documents_found", data_dir=str(data_dir))
        return 0
    chunks = chunk_documents(documents)

    store = get_vector_store(drop_old=rebuild)
    store.add_documents(chunks)
    logger.info(
        "ingestion_complete",
        collection=settings.milvus_collection,
        chunks=len(chunks),
        rebuild=rebuild,
    )
    return len(chunks)
