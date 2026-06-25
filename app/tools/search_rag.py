"""Tool: local company-data RAG search with ChromaDB.

This module lazily initializes a persistent Chroma collection, loads the
company seed text file, and searches it from the LangChain tool runtime.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from langchain_core.tools import tool


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_DIR = PROJECT_ROOT / ".chroma"
DEFAULT_SOURCE_FILE = PROJECT_ROOT / "data" / "company_vector_seed_kr_listed_20.txt"
FALLBACK_SOURCE_FILE = PROJECT_ROOT / "company_vector_seed_kr_listed_20.txt"
DEFAULT_COLLECTION_NAME = "company_research_data"

_CLIENT = None
_COLLECTION = None


class LocalHashEmbeddingFunction(EmbeddingFunction[Documents]):
    """Small local embedding function that works without model downloads.

    It is not as smart as a trained embedding model, but it is deterministic,
    dependency-light, and works well enough for Korean/English keyword-heavy
    company profiles. Chroma still handles vector storage and nearest-neighbor
    search; the hash vectors give it stable numeric representations.
    """

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _tokenize(text)

        for token in tokens:
            self._add_feature(vector, token, weight=1.0)
            if len(token) >= 4:
                for i in range(0, len(token) - 2):
                    self._add_feature(vector, token[i : i + 3], weight=0.45)

        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def _add_feature(self, vector: list[float], feature: str, weight: float) -> None:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        index = raw % self.dimensions
        sign = 1.0 if ((raw >> 9) & 1) else -1.0
        vector[index] += sign * weight


def _tokenize(text: str) -> list[str]:
    lowered = text.lower()
    return re.findall(r"[0-9a-zA-Z가-힣_./+-]+", lowered)


def _split_documents(text: str) -> list[tuple[str, str, dict]]:
    """Split seed text into Chroma documents using the '---' separator."""
    documents: list[tuple[str, str, dict]] = []
    chunks = [chunk.strip() for chunk in re.split(r"\n---\s*\n", text) if chunk.strip()]

    for index, chunk in enumerate(chunks):
        metadata = _extract_metadata(chunk)
        if not metadata.get("doc_id") and not metadata.get("회사명"):
            continue
        doc_id = metadata.get("doc_id") or f"rag-doc-{index:04d}"
        documents.append((doc_id, chunk, metadata))

    return documents


def _extract_metadata(chunk: str) -> dict:
    metadata: dict[str, str] = {}
    wanted_fields = {
        "doc_id",
        "회사명",
        "영문명",
        "종목코드",
        "거래소",
        "산업분류",
        "그룹/계열",
    }

    for line in chunk.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key in wanted_fields:
            metadata[key] = value.strip()

    return metadata


def _get_source_file() -> Path:
    source = os.getenv("RAG_SOURCE_FILE")
    if source:
        return Path(source).expanduser().resolve()
    if DEFAULT_SOURCE_FILE.exists():
        return DEFAULT_SOURCE_FILE
    if FALLBACK_SOURCE_FILE.exists():
        return FALLBACK_SOURCE_FILE
    return DEFAULT_SOURCE_FILE


def _get_chroma_dir() -> Path:
    chroma_dir = os.getenv("CHROMA_DB_DIR")
    if chroma_dir:
        return Path(chroma_dir).expanduser().resolve()
    return DEFAULT_CHROMA_DIR


def _init_collection():
    """Create/load the persistent Chroma collection and seed it if needed."""
    global _CLIENT, _COLLECTION

    if _COLLECTION is not None:
        return _COLLECTION

    chroma_dir = _get_chroma_dir()
    chroma_dir.mkdir(parents=True, exist_ok=True)

    _CLIENT = chromadb.PersistentClient(path=str(chroma_dir))
    _COLLECTION = _CLIENT.get_or_create_collection(
        name=os.getenv("CHROMA_COLLECTION_NAME", DEFAULT_COLLECTION_NAME),
        embedding_function=LocalHashEmbeddingFunction(),
        metadata={"description": "Korean listed-company research seed data"},
    )

    _seed_collection_if_needed(_COLLECTION)
    return _COLLECTION


def _seed_collection_if_needed(collection) -> None:
    source_file = _get_source_file()
    if not source_file.exists():
        print(f"[search_rag] source file not found: {source_file}")
        return

    source_mtime = str(int(source_file.stat().st_mtime))
    existing = collection.get(limit=1, include=["metadatas"])
    existing_metadata = (existing.get("metadatas") or [{}])[0] if existing.get("ids") else {}

    if existing.get("ids") and existing_metadata.get("source_mtime") == source_mtime:
        return

    text = source_file.read_text(encoding="utf-8-sig")
    parsed_documents = _split_documents(text)
    if not parsed_documents:
        print(f"[search_rag] no documents parsed from: {source_file}")
        return

    current_ids = collection.get(include=[]).get("ids", [])
    if current_ids:
        collection.delete(ids=current_ids)

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    for doc_id, document, metadata in parsed_documents:
        ids.append(doc_id)
        documents.append(document)
        metadatas.append(
            {
                **metadata,
                "source_file": str(source_file),
                "source_mtime": source_mtime,
            }
        )

    collection.add(ids=ids, documents=documents, metadatas=metadatas)
    print(f"[search_rag] ChromaDB seeded: {len(ids)} docs from {source_file}")


def _format_results(topic: str, results: dict) -> str:
    ids = (results.get("ids") or [[]])[0]
    documents = (results.get("documents") or [[]])[0]
    metadatas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]

    if not ids:
        return f"'{topic}' 관련 사내 벡터DB 검색 결과가 없습니다."

    lines = [f"'{topic}' 관련 사내 벡터DB 검색 결과:"]
    for rank, (doc_id, document, metadata, distance) in enumerate(
        zip(ids, documents, metadatas, distances),
        start=1,
    ):
        company = metadata.get("회사명", "회사명 없음")
        ticker = metadata.get("종목코드", "")
        industry = metadata.get("산업분류", "")
        score = 1 / (1 + distance) if distance is not None else 0
        excerpt = _make_excerpt(document, topic)

        header = f"{rank}. {company}"
        if ticker:
            header += f" ({ticker})"
        if industry:
            header += f" / {industry}"

        lines.append(header)
        lines.append(f"   doc_id: {doc_id}, relevance_score: {score:.3f}")
        lines.append(f"   {excerpt}")

    return "\n".join(lines)


def _make_excerpt(document: str, topic: str, max_chars: int = 700) -> str:
    topic_tokens = set(_tokenize(topic))
    paragraphs = [line.strip() for line in document.splitlines() if line.strip()]

    preferred: list[str] = []
    for paragraph in paragraphs:
        paragraph_tokens = set(_tokenize(paragraph))
        if topic_tokens & paragraph_tokens:
            preferred.append(paragraph)

    selected = preferred[:4] if preferred else paragraphs[:6]
    excerpt = " ".join(selected)
    if len(excerpt) > max_chars:
        return excerpt[: max_chars - 3].rstrip() + "..."
    return excerpt


@tool
def search_rag(topic: str) -> str:
    """사내 벡터DB에서 주제와 관련된 회사/산업 데이터를 검색합니다.

    Args:
        topic: 검색할 주제, 회사명, 종목코드, 산업 키워드.
    """
    print(f"\n[Tool 가동] search_rag -> {topic}")

    query = topic.strip()
    if not query:
        return "검색어가 비어 있습니다. 회사명, 종목코드, 산업 키워드 중 하나를 입력하세요."

    try:
        collection = _init_collection()
        if collection.count() == 0:
            return "사내 벡터DB에 검색할 문서가 없습니다. RAG_SOURCE_FILE 또는 회사 데이터 txt 파일을 확인하세요."

        results = collection.query(
            query_texts=[query],
            n_results=min(5, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        return _format_results(query, results)
    except Exception as exc:
        print(f"[search_rag] 검색 실패: {exc}")
        return f"사내 벡터DB 검색 중 오류가 발생했습니다: {exc}"
