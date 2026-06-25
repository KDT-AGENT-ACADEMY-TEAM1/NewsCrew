"""[노드] 검수 — 편집장 관점의 '체크리스트 기반' 자동 AI 검수.

  구조 체크(규칙)  : 제목/소제목/분량/형식 → 결정적으로 점수화
  카테고리 체크   : interest_category.checkpoints 항목별 LLM 채점 (없으면 공통 품질 항목)
  → 항목별 점수를 합산(총 100점)하고, 환경설정의 '승인 기준 점수(pass_score)'로 통과 판정.

검수 결과(점수/체크리스트 코멘트/상태)는 newsletter 테이블에 저장합니다.
이 노드까지가 '그래프 한 덩어리'이고, 직후 send 직전에서 멈춰 사람 승인을 받습니다.
"""
from __future__ import annotations

import json

from langgraph.config import get_config

from ..categories import get_checkpoints_for_categories
from ..db import execute, get_default_review_checkpoints, get_int_setting
from ..llm import ask_ai
from ..state import NewsletterState, ReviewResult


# 품질(LLM) 체크 항목: (키, 표시명, 평가 관점) — 배점은 항목 수에 맞춰 60점을 나눠 가집니다.
QUALITATIVE_ITEMS = [
    ("lead",    "도입부(리드)", "첫 문단이 독자의 흥미를 끌고 글의 핵심을 예고하는가"),
    ("tone",    "톤앤매너",     "친근하면서도 전문적인 어조가 일관되는가"),
    ("value",   "정보 가치",    "핵심 정보가 구체적이고 독자에게 유익한가(일반론만 아님)"),
    ("clarity", "명확성·간결성", "문장이 명확하고 군더더기 없이 이해하기 쉬운가"),
    ("closing", "마무리",       "맺음말 또는 다음 행동(관심·구독 등) 유도가 있는가"),
]
QUALITATIVE_TOTAL = 60   # 품질 항목 합계 점수


# ==========================================================================
# STEP 4. 검수 노드 — 체크리스트 채점 + 점수 저장
# ==========================================================================
def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    print(f"[검수] 체크리스트 AI 검수 시작 ({revision}회차)")

    # 카테고리에 등록된 체크포인트(쉼표·줄 단위)를 항목별로 검수합니다.
    cat_ids = list(state.get("category_ids") or [])
    cid = state.get("category_id")
    if cid and cid not in cat_ids:
        cat_ids.insert(0, cid)
    checkpoints = get_checkpoints_for_categories(cat_ids)
    checklist_source = "category"
    if not checkpoints:
        checkpoints = get_default_review_checkpoints()
        checklist_source = "default" if checkpoints else "fallback"
    if checkpoints:
        src = "카테고리" if checklist_source == "category" else "기본"
        print(f"[검수] {src} 체크포인트 {len(checkpoints)}개: {', '.join(checkpoints)}")
    score, checklist = _checklist_review(draft, checkpoints)
    pass_score = get_int_setting("pass_score", 60)
    passed = score >= pass_score

    head = (f"{'✅ 통과' if passed else '❌ 미달'} · 총점 {score}/100 "
            f"(기준 {pass_score}점) [체크:{checklist_source}]\n")
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


# ==========================================================================
# 체크리스트 채점 (구조 + 품질)
# ==========================================================================
def _checklist_review(draft: str, checkpoints: list[str] | None = None) -> tuple[int, str]:
    """체크리스트 항목별로 채점하고, (총점, 체크리스트 코멘트)를 돌려줍니다.

    checkpoints: 카테고리에 등록된 체크포인트 — 항목마다 개별 LLM 채점.
    """
    items = _structural_checks(draft) + _quality_checks(draft, checkpoints or [])
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


def _allocate_points(spec: list[tuple[str, str, str]], total: int) -> list[tuple[str, str, str, int]]:
    """채점 항목에 배점을 균등 분배합니다. (key, label, desc, pts)"""
    n = len(spec)
    if n == 0:
        return []
    base = total // n
    remainder = total - base * n
    return [
        (key, label, desc, base + (1 if i < remainder else 0))
        for i, (key, label, desc) in enumerate(spec)
    ]


def _build_quality_spec(checkpoints: list[str]) -> list[tuple[str, str, str, int]]:
    """채점할 품질/카테고리 항목 목록 (키, 표시명, 평가관점, 배점).

    카테고리 체크포인트가 있으면 등록된 항목마다 개별 채점합니다.
    없으면 공통 품질 항목(리드/톤 등)으로 대체합니다.
    """
    if checkpoints:
        spec = [
            (f"cp{i}", cp, f"다음 체크포인트를 충실히 반영했는가: {cp}")
            for i, cp in enumerate(checkpoints)
        ]
        return _allocate_points(spec, QUALITATIVE_TOTAL)

    spec = [(key, label, desc) for key, label, desc in QUALITATIVE_ITEMS]
    return _allocate_points(spec, QUALITATIVE_TOTAL)


def _quality_checks(draft: str, checkpoints: list[str]) -> list[dict]:
    """LLM 기반 카테고리 체크포인트(또는 공통 품질) 채점 — 총 60점."""
    spec = _build_quality_spec(checkpoints)

    # 분량이 너무 적으면 LLM 호출 없이 0점 처리
    if not draft or len(draft.strip()) < 80:
        return [_item(label, pts, 0, "본문이 비어 있거나 너무 짧습니다.")
                for _key, label, _desc, pts in spec]

    rubric = "\n".join(f"- {key}: {desc}" for key, _label, desc, _pts in spec)
    keys = ", ".join(f'"{key}"' for key, *_ in spec)
    skeleton = ", ".join(f'"{key}": {{"score": 0, "comment": ""}}' for key, *_ in spec)
    system = (
        "당신은 10년차 뉴스레터 편집장입니다. 아래 초안을 체크리스트 항목별로 0~100점으로 채점하세요.\n"
        f"[채점 항목]\n{rubric}\n\n"
        "반드시 아래 JSON 형식으로만 답하세요. 각 항목에 score(0~100 정수)와 짧은 comment(한국어 한 문장).\n"
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
        items.append(_item(label, pts, round(pts * ratio), comment[:80]))
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
