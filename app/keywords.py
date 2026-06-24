"""자연어 문장에서 검색 키워드 추출 (LLM 우선 + 규칙 폴백).

FastAPI(/keywords/extract)에서 사용합니다. (LLM 호출은 백엔드에서)
"""
from __future__ import annotations

import re

from .llm import ask_ai

# 키워드가 아닌, 자주 나오는 '요청/꾸밈' 단어들 (이 단어 자체는 버립니다)
STOPWORDS = {
    "뉴스", "소식", "정보", "기사", "내용", "관련", "주제", "오늘", "최근", "요즘",
    "정리", "요약", "작성", "생성", "만들", "만들어", "만들어줘", "해줘", "해주세요",
    "알려줘", "알려주세요", "보여줘", "보여주세요", "부탁", "부탁해", "부탁해요",
    "그리고", "또는", "관해", "대해", "대한", "위한", "좀", "것", "수",
}

# 단어 끝에 붙는 한글 조사 (긴 것부터 떼어 내야 정확합니다)
PARTICLES = (
    "이랑", "랑", "이나", "나", "에서", "에게", "에", "으로", "로",
    "은", "는", "이", "가", "을", "를", "와", "과", "도", "의", "께",
)

# 단어 끝에 이런 '요청 동사 어미'가 붙어 있으면 키워드가 아니라 부탁 표현으로 봅니다.
REQUEST_ENDINGS = (
    "해주세요", "해줘요", "해줘", "해주", "주세요", "줘요", "줘",
    "할게", "해요", "합니다", "해", "하기",
)


def _strip_particle(word: str) -> str:
    """단어 끝의 조사를 한 번 떼어 냅니다. (예: '전기차랑' → '전기차')"""
    for p in PARTICLES:
        if word.endswith(p) and len(word) - len(p) >= 2:
            return word[: -len(p)]
    return word


def extract_keywords(text: str) -> list[str]:
    """자연어 문장에서 핵심 키워드를 뽑아냅니다. (LLM → 실패 시 규칙 폴백)"""
    llm_keywords = _keywords_by_llm(text)
    if llm_keywords:
        return llm_keywords
    return _keywords_by_rule(text)


def _keywords_by_llm(text: str) -> list[str]:
    """LLM에게 자연어 문장에서 검색 키워드만 뽑아 달라고 시킵니다."""
    system = (
        "너는 뉴스 검색용 키워드 추출기다. "
        "사용자 문장에서 핵심 주제어(명사구)만 뽑아라. "
        "'뉴스/소식/정리해줘' 같은 요청·꾸밈 표현과 조사는 빼라. "
        "최대 4개를 한국어로, 쉼표(,)로만 구분해서 출력하라. "
        "설명·번호·따옴표 없이 키워드만 출력하라."
    )
    answer = ask_ai(system, text)
    if not answer or answer.startswith("[가짜 AI 답변]"):
        return []

    keywords: list[str] = []
    for part in answer.replace("\n", ",").split(","):
        kw = part.strip().strip("\"'·-•").strip()
        if kw and kw not in keywords:
            keywords.append(kw)
    return keywords[:4]


def _keywords_by_rule(text: str) -> list[str]:
    """규칙 기반 키워드 추출 (LLM 폴백용)."""
    cleaned = re.sub(r"[^0-9A-Za-z가-힣\s]", " ", text)   # 기호 제거

    keywords: list[str] = []
    for raw in cleaned.split():
        if raw.endswith(REQUEST_ENDINGS):                  # '~해줘/~주세요' 버림
            continue
        word = _strip_particle(raw)                        # 조사 떼기
        if len(word) < 2 or word in STOPWORDS:             # 불용어·1글자 거르기
            continue
        if word not in keywords:                           # 중복 제거
            keywords.append(word)
    return keywords[:4]
