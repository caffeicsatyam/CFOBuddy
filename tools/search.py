import logging
import os
import time
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.tools import tool
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
from llama_index.llms.groq import Groq
from llama_index.vector_stores.postgres import PGVectorStore
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel
from sqlalchemy import make_url

from tools.reranker import rerank_docs

load_dotenv()

logger = logging.getLogger(__name__)
TABLE_NAME = "data_cfo_buddy_vectors"
_settings_configured = False


def _configure_settings() -> None:
    global _settings_configured

    if _settings_configured:
        return

    embed_api_key = os.getenv("NVIDIA_EMBEDDING_API_KEY")
    if embed_api_key:
        try:
            from llama_index.embeddings.nvidia import NVIDIAEmbedding

            Settings.embed_model = NVIDIAEmbedding(
                model="nvidia/nv-embed-v1",
                api_key=embed_api_key,
            )
        except ImportError:
            logger.warning(
                "llama_index NVIDIA embedding package is unavailable; falling back to HuggingFace embeddings."
            )
            from llama_index.embeddings.huggingface import HuggingFaceEmbedding

            Settings.embed_model = HuggingFaceEmbedding(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                embed_batch_size=32,
            )
    else:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        Settings.embed_model = HuggingFaceEmbedding(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            embed_batch_size=32,
        )

    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        Settings.llm = Groq(
            model="llama-3.1-8b-instant",
            api_key=groq_api_key,
            temperature=0.2,
        )

    _settings_configured = True


@lru_cache(maxsize=1)
def get_vector_store() -> PGVectorStore:
    connection_string = os.getenv("DATABASE_URL")
    if not connection_string:
        raise RuntimeError("DATABASE_URL is not set")

    url = make_url(connection_string)
    return PGVectorStore.from_params(
        database=url.database,
        host=url.host,
        password=url.password,
        port=url.port or 5432,
        user=url.username,
        table_name=TABLE_NAME,
        embed_dim=4096,
        hybrid_search=True,
        text_search_config="english",
    )


@lru_cache(maxsize=1)
def get_index() -> VectorStoreIndex:
    _configure_settings()
    return VectorStoreIndex.from_vector_store(get_vector_store())


def reload_index() -> None:
    get_index.cache_clear()
    logger.info("Index reloaded")


def clean_query(query: str) -> str:
    return query.strip()


def _extract_text(node: object) -> str:
    for attr in ("get_text", "get_content", "text", "content", "page_content"):
        if hasattr(node, attr):
            value = getattr(node, attr)
            try:
                return value() if callable(value) else str(value)
            except Exception:
                continue

    if hasattr(node, "node") and hasattr(node.node, "text"):
        return str(node.node.text)

    return str(node)


class SearchInput(BaseModel):
    query: str


@tool(args_schema=SearchInput)
def search_financial_docs(query: str, config: RunnableConfig) -> str:
    """Search internal financial documents using hybrid semantic + keyword search."""

    start = time.time()
    query = clean_query(query)
    username = config.get("configurable", {}).get("username", "admin")
    filters = MetadataFilters(filters=[ExactMatchFilter(key="username", value=username)])

    try:
        index = get_index()
    except Exception as exc:
        logger.exception("Search backend is not ready")
        return f"Search is unavailable right now: {exc}"

    try:
        retriever = index.as_retriever(
            similarity_top_k=10,
            similarity_cutoff=0.0,
            vector_store_query_mode="hybrid",
            filters=filters,
        )
        candidates = retriever.retrieve(query)
    except Exception as exc:
        logger.exception("Retriever failed, falling back to compact query engine: %s", exc)
        try:
            query_engine = index.as_query_engine(filters=filters, response_mode="compact")
            response = query_engine.query(query)
            return str(response)
        except Exception as query_exc:
            logger.exception("Fallback query engine also failed: %s", query_exc)
            return f"Search failed: {query_exc}"

    texts = [_extract_text(candidate) for candidate in candidates]

    try:
        reranked = rerank_docs(query, texts, top_k=5)
    except Exception as exc:
        logger.exception("Reranker failed: %s", exc)
        reranked = []

    try:
        query_engine = index.as_query_engine(similarity_top_k=5, filters=filters, response_mode="compact")
        response = query_engine.query(query)
    except Exception as exc:
        logger.exception("Query engine failed: %s", exc)
        return f"Search failed: {exc}"

    elapsed = (time.time() - start) * 1000
    logger.info("search_financial_docs completed in %.2f ms", elapsed)

    output_parts = [str(response)]
    if reranked:
        output_parts.append("\nTop reranked documents:\n")
        for item in reranked:
            doc_text = str(item.get("doc", ""))
            score = float(item.get("score", 0.0))
            snippet = doc_text[:1000] + "..." if len(doc_text) > 1000 else doc_text
            output_parts.append(f"Score: {score:.4f}\n{snippet}\n")

    return "\n".join(output_parts)
