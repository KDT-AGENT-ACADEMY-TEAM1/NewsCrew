"""내부 자료(data/관련규정, data/관련자료)를 Chroma 벡터DB에 임베딩하고 검색합니다.

  - init_chroma() : 컬렉션이 비어 있으면 data 아래 txt/pdf 를 읽어 임베딩(최초 1회).
  - search(query) : 질의와 가장 유사한 내부 자료 조각들을 돌려줍니다.

임베딩은 chromadb 기본 임베딩 함수(MiniLM, onnxruntime)를 사용합니다. (OpenAI 키 불필요)
저장 위치는 환경변수 CHROMA_DIR 로 바꿀 수 있습니다. (기본: 프로젝트/chroma_db)
"""
from __future__ import annotations

import glob
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 프로젝트 루트
_DATA_DIRS = [
    os.path.join(_ROOT, "data", "관련규정"),
    os.path.join(_ROOT, "data", "관련자료"),
]
_CHROMA_DIR = os.getenv("CHROMA_DIR", os.path.join(_ROOT, "chroma_db"))
_COLLECTION = "internal_docs"

_collection = None   # 한 번 만든 컬렉션을 재사용


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        client = chromadb.PersistentClient(path=_CHROMA_DIR)
        _collection = client.get_or_create_collection(_COLLECTION)
    return _collection


# --------------------------- 파일 읽기 ---------------------------
def _read_txt(path: str) -> str:
    for enc in ("utf-8", "cp949"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


def _read_pdf(path: str) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:
        print(f"[chroma] PDF 읽기 실패 {os.path.basename(path)}: {e}")
        return ""


def _chunk(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    """긴 글을 검색하기 좋게 일정 길이로 쪼갭니다. (겹침 overlap 으로 맥락 유지)"""
    text = " ".join((text or "").split())
    if not text:
        return []
    chunks, i = [], 0
    while i < len(text):
        chunks.append(text[i:i + size])
        i += size - overlap
    return chunks


def _iter_files():
    for d in _DATA_DIRS:
        for path in sorted(glob.glob(os.path.join(d, "*"))):
            ext = os.path.splitext(path)[1].lower()
            if ext == ".txt":
                yield path, _read_txt(path)
            elif ext == ".pdf":
                yield path, _read_pdf(path)


# --------------------------- 색인 / 검색 ---------------------------
def init_chroma(force: bool = False) -> int:
    """내부 자료를 Chroma 에 임베딩합니다. (이미 색인돼 있으면 건너뜀 — 임베딩된 조각 수 반환)

    force=True 면 컬렉션을 비우고 다시 색인합니다.
    """
    global _collection
    print("=" * 60)
    print(f"[chroma] 내부자료 색인 시작 (force={force})")
    print(f"[chroma] 저장 위치: {_CHROMA_DIR}")
    print(f"[chroma] 자료 폴더: {', '.join(_DATA_DIRS)}")
    try:
        import chromadb
        client = chromadb.PersistentClient(path=_CHROMA_DIR)
        if force:
            try:
                client.delete_collection(_COLLECTION)
                print("[chroma] 기존 컬렉션 삭제(재색인)")
            except Exception:
                pass
            _collection = None
        col = client.get_or_create_collection(_COLLECTION)
        _collection = col
    except Exception as e:
        print(f"[chroma] 초기화 실패(건너뜀): {e}")
        print("=" * 60)
        return 0

    if col.count() > 0:               # 이미 색인됨
        print(f"[chroma] 이미 색인되어 있어 건너뜁니다. (조각 수: {col.count()})")
        print("=" * 60)
        return col.count()

    docs, ids, metas = [], [], []
    file_count = 0
    for path, text in _iter_files():
        name = os.path.basename(path)
        n = 0
        for i, chunk in enumerate(_chunk(text)):
            docs.append(chunk)
            ids.append(f"{name}::{i}")
            metas.append({"source": name})
            n += 1
        file_count += 1
        print(f"[chroma]   읽음: {name}  ({len(text):,}자 → {n}조각)")

    if docs:
        print(f"[chroma] 임베딩 중... 파일 {file_count}개 / 조각 {len(docs)}개 "
              f"(최초 1회 모델 다운로드로 시간이 걸릴 수 있습니다)")
        try:
            col.add(documents=docs, ids=ids, metadatas=metas)
            print(f"[chroma] ✅ 임베딩 완료: {col.count()} 조각")
        except Exception as e:
            print(f"[chroma] ❌ 임베딩 실패: {e}")
    else:
        print("[chroma] 임베딩할 내부 자료가 없습니다. (data/관련규정, data/관련자료 확인)")
    print("=" * 60)
    return col.count()


def count() -> int:
    try:
        return _get_collection().count()
    except Exception:
        return 0


def search(query: str, k: int = 3) -> list[dict]:
    """질의와 유사한 내부 자료 조각을 돌려줍니다. → [{source, text}, ...]"""
    try:
        col = _get_collection()
        if col.count() == 0:
            return []
        res = col.query(query_texts=[query], n_results=k)
    except Exception as e:
        print(f"[chroma] 검색 실패: {e}")
        return []

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    out = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) and metas[i] else {}
        out.append({"source": meta.get("source", "내부자료"), "text": doc})
    return out
