import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from llama_index.core import Settings, SimpleDirectoryReader, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import DocxReader, PandasCSVReader, PandasExcelReader, PDFReader
from llama_index.vector_stores.postgres import PGVectorStore

from cfobuddy_logging import configure_logging

load_dotenv()
logger = configure_logging()

DATA_FOLDER = "data"
TABLE_NAME = "data_cfo_buddy_vectors"
ALLOWED_EXTENSIONS = {".csv", ".pdf", ".xlsx", ".xls", ".docx"}
INDEX_MANIFEST_PATH = Path(DATA_FOLDER) / ".index_manifest.json"


def _file_extractors() -> dict[str, object]:
    return {
        ".docx": DocxReader(),
        ".csv": PandasCSVReader(),
        ".pdf": PDFReader(),
        ".xlsx": PandasExcelReader(),
        ".xls": PandasExcelReader(),
    }


def _configure_embed_model() -> None:
    nvidia_api_key = os.getenv("NVIDIA_EMBEDDING_API_KEY")

    if nvidia_api_key:
        try:
            from llama_index.embeddings.nvidia import NVIDIAEmbedding

            Settings.embed_model = NVIDIAEmbedding(
                model="nvidia/nv-embed-v1",
                api_key=nvidia_api_key,
            )
            return
        except ImportError:
            logger.warning(
                "llama_index NVIDIA embedding package is unavailable; falling back to HuggingFace embeddings."
            )

    from llama_index.embeddings.huggingface import HuggingFaceEmbedding

    Settings.embed_model = HuggingFaceEmbedding(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        embed_batch_size=32,
    )


def _load_manifest() -> dict[str, dict[str, object]]:
    if not INDEX_MANIFEST_PATH.exists():
        return {}

    try:
        data = json.loads(INDEX_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Index manifest is unreadable; rebuilding requested files.")
        return {}

    return data if isinstance(data, dict) else {}


def _save_manifest(manifest: dict[str, dict[str, object]]) -> None:
    INDEX_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_files(input_files: Iterable[str | Path] | None) -> list[Path]:
    if input_files is None:
        root = Path(DATA_FOLDER)
        if not root.exists():
            return []
        files = [path for path in root.rglob("*") if path.is_file()]
    else:
        files = [Path(path) for path in input_files]

    return [
        path
        for path in files
        if path.exists() and path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    ]


def _delete_previous_vectors(
    vector_store: PGVectorStore,
    manifest_entry: dict[str, object] | None,
) -> None:
    if not manifest_entry:
        return

    doc_ids = manifest_entry.get("doc_ids")
    if not isinstance(doc_ids, list):
        return

    for doc_id in doc_ids:
        if not isinstance(doc_id, str):
            continue
        try:
            vector_store.delete(doc_id)
        except Exception:
            logger.warning("Failed to delete previous vectors for %s", doc_id, exc_info=True)


def build_index(
    input_files: Iterable[str | Path] | None = None,
    force: bool = False,
) -> int:
    """Build and store hybrid vectors in Neon DB.

    When input_files is provided, only those files are considered. A local
    manifest skips unchanged files so uploads do not re-embed the entire data
    folder.
    """

    _configure_embed_model()
    Settings.llm = None
    Settings.node_parser = SentenceSplitter(
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "150")),
    )

    vector_store = PGVectorStore.from_params(
        host=os.getenv("NEON_HOST"),
        database=os.getenv("NEON_DATABASE"),
        user=os.getenv("NEON_USER"),
        password=os.getenv("NEON_PASSWORD"),
        port="5432",
        table_name=TABLE_NAME,
        embed_dim=4096,
        hybrid_search=True,
        text_search_config="english",
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    manifest = _load_manifest()
    candidates = _candidate_files(input_files)

    if not candidates:
        logger.info("No supported documents found for indexing.")
        return 0

    files_to_index = []
    file_hashes = {}
    for path in candidates:
        resolved = path.resolve()
        key = str(resolved)
        digest = _file_hash(resolved)
        file_hashes[key] = digest

        if not force and manifest.get(key, {}).get("sha256") == digest:
            logger.info("Skipping unchanged document: %s", path)
            continue

        _delete_previous_vectors(vector_store, manifest.get(key))
        files_to_index.append(resolved)

    if not files_to_index:
        logger.info("All candidate documents are already indexed.")
        return 0

    logger.info("Loading %d changed document(s) for indexing...", len(files_to_index))

    documents = SimpleDirectoryReader(
        input_files=[str(path) for path in files_to_index],
        filename_as_id=True,
        file_extractor=_file_extractors(),
    ).load_data(show_progress=True)

    if not documents:
        logger.info("No indexable content found in changed document(s).")
        return 0

    doc_ids_by_path: dict[str, list[str]] = {str(path): [] for path in files_to_index}
    for doc in documents:
        indexed_at = datetime.datetime.now().isoformat()
        doc.metadata["indexed_at"] = indexed_at
        file_path = doc.metadata.get("file_path")
        if file_path:
            resolved_file_path = str(Path(str(file_path)).resolve())
            doc.metadata["source_path"] = resolved_file_path
            doc_ids_by_path.setdefault(resolved_file_path, []).append(doc.id_)

    logger.info("Building index with %d documents...", len(documents))

    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True,
    )

    for path in files_to_index:
        key = str(path)
        manifest[key] = {
            "sha256": file_hashes[key],
            "indexed_at": datetime.datetime.now().isoformat(),
            "doc_ids": doc_ids_by_path.get(key, []),
        }

    _save_manifest(manifest)

    logger.info("Index built successfully with %d document(s)!", len(documents))
    return len(documents)


if __name__ == "__main__":
    build_index()
