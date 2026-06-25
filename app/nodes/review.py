"""[노드] 검수 — 편집장 관점의 '체크리스트 기반' 자동 AI 검수.

구조 체크(규칙)  : 제목/소제목/분량/형식 → 결정적으로 점수화 (40점 만점)
품질 체크(LLM)   : 리드/톤앤매너/정보가치/명확성/마무리 + 카테고리 체크포인트 + 타입 적합성 → ask_ai 로 평가 (60점 만점)
→ 항목별 점수를 합산(총 100점)하고, 환경설정의 '승인 기준 점수(pass_score)'로 통과 판정.
"""
from __future__ import annotations

import json

from langgraph.config import get_config

from ..categories import get_checkpoints
from ..db import execute, fetch_one, get_int_setting
from ..llm import ask_ai
from ..state import NewsletterState, ReviewResult

# 품질(LLM) 체크 항목: (키, 표시명, 평가 관점) — 배점은 항목 수에 맞춰 60점을 나눠 가집니다.
QUALITATIVE_ITEMS = [
    ("lead",    "도입부(리드)", "첫 문단이 독자의 흥미를 끌고 글의 핵심을 예고하는가"),
    ("tone",    "톤앤매너",     "친근하면서도 전문적인 어조가 일관되는가"),
    ("value",   "정보 가치",    "핵심 정보가 구체적이고 독자에게 유익한가(일반론만 아님)"),
    ("clarity", "명확성·간결성", "문장이 명확하고 군더더기 없이 이해하기 쉬운가"),
    ("closing", "마무리",       "맺음말 또는 다음 행동(관심·구독 등) 유도가 있는가"),
    ("summary_clarity", "핵심 요약 명확성", "글 전체를 관통하는 핵심 메시지(Key Takeaway)나 구체적인 행동 지침(Action Item)이 명확히 제시되어 있는가"),
    ("hallucination_filter", "할루시네이션 필터링", "구체적인 출처(기관, 전문가, 보고서 등) 없이 '최근 통계에 의하면' 등의 모호한 표현을 남발하지 않는가")
]
QUALITATIVE_TOTAL = 60   # 품질 항목 합계 점수


def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    type_code = state.get("type_code")

    # 1. DB에서 타입명과 타입 설명 조회 (HEAD 기능 통합)
    type_name = ""
    type_desc = ""
    if type_code:
        row = fetch_one("SELECT name, description FROM newsletter_type WHERE code = %s", (type_code,))
        if row:
            type_name = row.get("name") or ""
            type_desc = row.get("description") or ""

    print(f"[검수] 체크리스트 AI 검수 시작 ({revision}회차)")

    # 2. 카테고리 체크포인트 가져오기 (main 기능)
    checkpoints = get_checkpoints(state.get("category_id"))

    # 3. 통합 체크리스트 검수 수행
    score, checklist = _checklist_review(draft, checkpoints, type_name, type_desc)
    pass_score = get_int_setting("pass_score", 60)
    passed = score >= pass_score

    # 4. 결과 포맷 가공 (main 포맷 준수)
    head = (f"{'✅ 통과' if passed else '❌ 미달'} · 총점 {score}/100 "
            f"(기준 {pass_score}점)\n")
    feedback = (head + checklist)[:990]   # review_feedback 컬럼(VARCHAR 1000) 보호
    review: ReviewResult = {"passed": passed, "score": score, "feedback": feedback}

    revision_count = revision + 1
    status = "awaiting_approval" if passed else "writing"
    print(f"[검수] 결과: {'통과' if passed else '미달'} (점수 {score} / 기준 {pass_score})")
    
    _save_review(review, status, revision_count)
    return {
        "review": review,
        "revision_count": revision_count,
        "status": status,
        "human_feedback": "",   # 피드백은 한 번 쓰고 비웁니다
    }


def _checklist_review(
    draft: str,
    checkpoints: list[str] | None = None,
    type_name: str = "",
    type_desc: str = ""
) -> tuple[int, str]:
    """체크리스트 항목별로 채점하고, (총점, 체크리스트 코멘트)를 돌려줍니다."""
    items = _structural_checks(draft) + _quality_checks(draft, checkpoints or [], type_name, type_desc)
    total = sum(it["score"] for it in items)
    lines = []
    for it in items:
        mark = "✅" if it["score"] >= it["max"] else ("⚠️" if it["score"] > 0 else "❌")
        lines.append(f"{mark} {it['label']} {it['score']}/{it['max']} — {it['comment']}")
    return total, "\n".join(lines)


def _item(label: str, max_pts: int, score: int, comment: str) -> dict:
    return {"label": label, "max": max_pts, "score": max(0, min(score, max_pts)),
            "comment": comment}


def _structural_checks(draft: str) -> list[dict]:
    """규칙 기반 구조 체크 (제목/소제목/분량/형식) — 총 40점."""
    text = draft or ""
    lines = text.split("\n")
    has_title = any(ln.startswith("# ") for ln in lines)
    section_count = sum(1 for ln in lines if ln.startswith("## "))
    length = len(text.strip())
    has_bullets = any(ln.strip().startswith(("- ", "* ")) for ln in lines)
    paragraphs = [b for b in text.split("\n\n") if b.strip()]

    items: list[dict] = []
    items.append(_item(
        "제목", 10, 10 if has_title else 0,
        "맨 위 '# 제목'이 있습니다." if has_title else "맨 위 '# 제목' 줄이 필요합니다."))

    sec_pts = 10 if section_count >= 2 else (5 if section_count == 1 else 0)
    items.append(_item(
        "소제목 구성", 10, sec_pts,
        f"소제목(##) {section_count}개." + ("" if section_count >= 2 else " 2개 이상 권장.")))

    len_pts = 10 if length >= 400 else (6 if length >= 200 else 2)
    items.append(_item(
        "분량", 10, len_pts,
        f"본문 {length}자." + ("" if length >= 400 else " 다소 짧습니다(400자+ 권장).")))

    fmt_pts = 10 if (has_bullets or len(paragraphs) >= 3) else 5
    items.append(_item(
        "가독성 형식", 10, fmt_pts,
        "목록/문단 구분이 적절합니다." if fmt_pts == 10 else "문단 나눔이나 목록을 더 활용하세요."))
    return items


def _build_quality_spec(checkpoints: list[str], type_name: str = "", type_desc: str = "") -> list[tuple]:
    """채점할 품질 항목 목록 (키, 표시명, 평가관점, 배점)을 만듭니다."""
    spec = list(QUALITATIVE_ITEMS)   # (키, 표시명, 평가관점)
    if checkpoints:
        desc = "이 분야의 핵심 체크포인트를 충실히 다뤘는가 — " + "; ".join(checkpoints)
        spec.append(("checkpoints", "주제 체크포인트", desc))
    
    if type_name:
        desc = f"뉴스레터 타입 '{type_name}'의 스타일 가이드를 준수했는가 — {type_desc}"
        spec.append(("style_guide", "타입 적합성", desc))

    n = len(spec)
    base = QUALITATIVE_TOTAL // n
    remainder = QUALITATIVE_TOTAL - base * n
    out = []
    for i, (key, label, desc) in enumerate(spec):
        pts = base + (1 if i < remainder else 0)   # 나머지는 앞쪽 항목에 1점씩
        out.append((key, label, desc, pts))
    return out


def _quality_checks(draft: str, checkpoints: list[str], type_name: str = "", type_desc: str = "") -> list[dict]:
    """LLM 기반 품질 체크 (리드/톤/가치/명확성/마무리 + 주제 체크포인트 + 타입 적합성) — 총 60점."""
    spec = _build_quality_spec(checkpoints, type_name, type_desc)

    # 분량이 너무 적으면 LLM 호출 없이 0점 처리
    if not draft or len(draft.strip()) < 80:
        return [_item(label, pts, 0, "본문이 비어 있거나 너무 짧습니다.")
                for _key, label, _desc, pts in spec]

    rubric = "\n".join(f"- {key}: {desc}" for key, _label, desc, _pts in spec)
    keys = ", ".join(f'"{key}"' for key, *_ in spec)
    skeleton = ", ".join(f'"{key}": {{"score": 0, "comment": ""}}' for key, *_ in spec)
    system = (
        "당신은 10년차 뉴스레터 편집장입니다. 아래 초안을 체크리스트 항목별로 0~100점으로 엄격하게 채점하세요.\n"
        "특히 100점 미만으로 감점된 모든 항목에 대해서는, '초안의 어느 문장/표현이 부족하여 감점되었는지' 구체적인 문제점과 수정 가이드를 comment에 한국어로 명확히 작성해야 합니다. (100점 만점인 경우에만 강점/칭찬 작성)\n"
        "각 comment는 공백 포함 100자 내외의 완성된 문장으로 작성해야 합니다.\n\n"
        f"[채점 항목]\n{rubric}\n\n"
        "반드시 아래 JSON 형식으로만 답하세요. 각 항목에 score(0~100 정수)와 구체적인 comment.\n"
        "{ " + skeleton + " }\n"
        f"(키는 정확히 {keys} 만 사용)"
    )
    answer = ask_ai(system, f"--- 뉴스레터 초안 ---\n{draft}")

    # 가짜 모드 → 안전 기본값(중상 점수)으로 통과 흐름 유지
    if not answer or answer.startswith("[가짜 AI 답변]"):
        return [_item(label, pts, int(pts * 0.75), "테스트 모드: 임시 점수")
                for _key, label, _desc, pts in spec]
    try:
        clean = answer.strip().replace("```json", "").replace("```", "")
        data = json.loads(clean)
    except Exception as e:
        print(f"[검수] 품질 JSON 파싱 실패 → 기본값 사용: {e}")
        return [_item(label, pts, int(pts * 0.6), "AI 응답 해석 실패로 기본 점수 적용")
                for _key, label, _desc, pts in spec]

    items: list[dict] = []
    for key, label, _desc, pts in spec:
        raw = data.get(key) or {}
        try:
            ratio = max(0, min(int(raw.get("score", 0)), 100)) / 100
        except (TypeError, ValueError):
            ratio = 0.6
        comment = str(raw.get("comment") or "").strip() or "-"
        items.append(_item(label, pts, round(pts * ratio), comment[:120]))
    return items


def _save_review(review: ReviewResult, status: str, revision_count: int) -> None:
    """검수 점수/코멘트/상태를 newsletter 테이블에 갱신합니다.

    write 노드가 먼저 만들어 둔 같은 thread_id 행을 UPDATE 합니다.
    thread_id 는 그래프 실행 설정(get_config)에서 가져옵니다. (best-effort)
    """
    try:
        thread_id = (get_config().get("configurable") or {}).get("thread_id")
    except Exception:
        thread_id = None      # 그래프 밖 단독 호출(예: 테스트)이면 저장 생략
    if not thread_id:
        return
    try:
        execute(
            "UPDATE newsletter "
            "SET review_score = %s, review_feedback = %s, status = %s, revision_count = %s "
            "WHERE thread_id = %s",
            (review.get("score"), review.get("feedback"), status, revision_count, thread_id),
        )
    except Exception as e:
        print(f"[검수] 점수 DB 저장 실패(무시하고 진행): {e}")
