"""[노드] 검수 — 편집장 관점의 '체크리스트 기반' 자동 AI 검수.

  구조 체크(규칙)  : 제목/소제목/분량/형식 → 결정적으로 점수화
  카테고리 체크   : interest_category.checkpoints 항목별 LLM 채점
                    (없으면 DB 기본 체크리스트 → 공통 품질 항목)
  → 항목별 점수를 합산(총 100점)하고, 환경설정의 '승인 기준 점수(pass_score)'로 통과 판정.
"""
from __future__ import annotations

import json
import re

from langgraph.config import get_config

from ..categories import get_checkpoints_for_categories
from ..db import execute, fetch_one, get_default_review_checkpoints, get_int_setting
from ..llm import ask_ai
from ..state import NewsletterState, ReviewResult

QUALITATIVE_ITEMS = [
    ("lead",    "도입부(리드)", "첫 문단이 독자의 흥미를 끌고 글의 핵심을 예고하는가"),
    ("tone",    "톤앤매너",     "친근하면서도 전문적인 어조가 일관되는가"),
    ("value",   "정보 가치",    "핵심 정보가 구체적이고 독자에게 유익한가(일반론만 아님)"),
    ("clarity", "명확성·간결성", "문장이 명확하고 군더더기 없이 이해하기 쉬운가"),
    ("closing", "마무리",       "맺음말 또는 다음 행동(관심·구독 등) 유도가 있는가"),
]
QUALITATIVE_TOTAL = 60


def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    type_code = state.get("type_code")

    type_name = ""
    type_desc = ""
    if type_code:
        row = fetch_one("SELECT name, description FROM newsletter_type WHERE code = %s", (type_code,))
        if row:
            type_name = row.get("name") or ""
            type_desc = row.get("description") or ""

    print(f"[검수] 체크리스트 AI 검수 시작 ({revision}회차)")

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

    score, checklist, items = _checklist_review(draft, checkpoints, type_name, type_desc)
    pass_score = get_int_setting("pass_score", 60)
    passed = score >= pass_score

    head = (f"{'✅ 통과' if passed else '❌ 미달'} · 총점 {score}/100 "
            f"(기준 {pass_score}점) [체크:{checklist_source}]\n")
    revision_count = revision + 1
    max_rev = state.get("max_revisions", 2)
    status = "awaiting_approval" if passed or revision_count >= max_rev else "writing"
    suggested_fix = _suggested_fix(items)
    feedback = _build_feedback(head, checklist, suggested_fix)
    review: ReviewResult = {
        "passed": passed,
        "score": score,
        "feedback": feedback,
        "deduction_reasons": _deduction_reasons(items),
        "suggested_fix": suggested_fix,
    }

    print(f"[검수] 결과: {'통과' if passed else '미달'} (점수 {score} / 기준 {pass_score})")
    _save_review(review, status, revision_count)
    return {
        "review": review,
        "revision_count": revision_count,
        "status": status,
        "human_feedback": "",
    }


def _checklist_review(
    draft: str,
    checkpoints: list[str] | None = None,
    type_name: str = "",
    type_desc: str = "",
) -> tuple[int, str, list[dict]]:
    items = _structural_checks(draft) + _quality_checks(
        draft, checkpoints or [], type_name, type_desc,
    )
    total = sum(it["score"] for it in items)
    lines = []
    for it in items:
        mark = "✅" if it["score"] >= it["max"] else ("⚠️" if it["score"] > 0 else "❌")
        lines.append(f"{mark} {it['label']} {it['score']}/{it['max']} — {it['comment']}")
    return total, "\n".join(lines), items


def _item(label: str, max_pts: int, score: int, comment: str, key: str = "") -> dict:
    return {"key": key, "label": label, "max": max_pts, "score": max(0, min(score, max_pts)),
            "comment": comment}


def _plain_text_len(text: str) -> int:
    """마크다운 장식을 일부 제거한 본문 글자 수."""
    cleaned = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"[*_`>\-]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    return len(cleaned)


def _structural_checks(draft: str) -> list[dict]:
    text = draft or ""
    lines = text.splitlines()
    stripped_lines = [ln.strip() for ln in lines if ln.strip()]
    first_line = stripped_lines[0] if stripped_lines else ""
    has_title = first_line.startswith("# ") and not first_line.startswith("## ")
    section_count = sum(
        1 for ln in stripped_lines
        if ln.startswith("## ") and not ln.startswith("### ")
    )
    length = _plain_text_len(text)
    has_bullets = any(
        re.match(r"^([-*]\s+|\d+\.\s+)", ln)
        for ln in stripped_lines
    )
    paragraphs = [
        block.strip()
        for block in re.split(r"\n\s*\n", text)
        if block.strip() and not block.strip().startswith("#")
    ]

    items: list[dict] = []
    items.append(_item(
        "제목", 10, 10 if has_title else 0,
        "첫 줄에 '# 제목'이 있습니다." if has_title else "첫 번째 줄에 '# 제목' 형식의 제목이 필요합니다.",
        "structure_title"))
    sec_pts = 10 if section_count >= 2 else (4 if section_count == 1 else 0)
    items.append(_item(
        "소제목 구성", 10, sec_pts,
        f"소제목(##) {section_count}개." + ("" if section_count >= 2 else " 2개 이상 필요합니다."),
        "structure_sections"))
    len_pts = 10 if length >= 400 else (6 if length >= 250 else (3 if length >= 120 else 0))
    items.append(_item(
        "분량", 10, len_pts,
        f"본문 {length}자." + ("" if length >= 400 else " 400자 이상을 권장합니다."),
        "readability_length"))
    fmt_pts = 10 if (has_bullets or len(paragraphs) >= 3) else 5
    items.append(_item(
        "가독성 형식", 10, fmt_pts,
        "목록 또는 문단 구분이 적절합니다." if fmt_pts == 10 else "목록, 번호 목록, 문단 구분을 더 활용하세요.",
        "readability_format"))
    return items


def _allocate_points(spec: list[tuple[str, str, str]], total: int) -> list[tuple[str, str, str, int]]:
    n = len(spec)
    if n == 0:
        return []
    base = total // n
    remainder = total - base * n
    return [
        (key, label, desc, base + (1 if i < remainder else 0))
        for i, (key, label, desc) in enumerate(spec)
    ]


def _build_quality_spec(
    checkpoints: list[str],
    type_name: str = "",
    type_desc: str = "",
) -> list[tuple[str, str, str, int]]:
    spec = [(key, label, desc) for key, label, desc in QUALITATIVE_ITEMS]
    spec.extend(
        (f"cp{i}", cp, f"다음 체크포인트를 충실히 반영했는가: {cp}")
        for i, cp in enumerate(checkpoints or [], start=1)
    )
    if type_name:
        spec.append((
            "style_guide",
            "타입 적합성",
            f"뉴스레터 타입 '{type_name}'의 스타일 가이드를 준수했는가 — {type_desc}",
        ))
    return _allocate_points(spec, QUALITATIVE_TOTAL)


def _quality_checks(
    draft: str,
    checkpoints: list[str],
    type_name: str = "",
    type_desc: str = "",
) -> list[dict]:
    spec = _build_quality_spec(checkpoints, type_name, type_desc)

    if not draft or len(draft.strip()) < 80:
        return [_item(label, pts, 0, "본문이 비어 있거나 너무 짧습니다.", key)
                for key, label, _desc, pts in spec]

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

    if not answer or answer.startswith("[가짜 AI 답변]"):
        return [_item(label, pts, int(pts * 0.3), "테스트 모드: 실제 LLM 검수가 실행되지 않았습니다.", key)
                for key, label, _desc, pts in spec]
    try:
        clean = _extract_json(answer)
        data = json.loads(clean)
    except Exception as e:
        print(f"[검수] 품질 JSON 파싱 실패 → 기본값 사용: {e}")
        return [_item(label, pts, int(pts * 0.3), "AI 응답 해석 실패로 검수 통과를 보류합니다.", key)
                for key, label, _desc, pts in spec]

    items: list[dict] = []
    for key, label, _desc, pts in spec:
        raw = data.get(key) or {}
        try:
            ratio = max(0, min(int(raw.get("score", 0)), 100)) / 100
        except (TypeError, ValueError):
            ratio = 0.6
        comment = str(raw.get("comment") or "").strip() or "-"
        items.append(_item(label, pts, round(pts * ratio), comment[:120], key))
    return items


def _extract_json(answer: str) -> str:
    clean = answer.strip().replace("```json", "").replace("```", "").strip()
    start = clean.find("{")
    end = clean.rfind("}")
    if start != -1 and end != -1 and end > start:
        return clean[start:end + 1]
    return clean


def _deduction_reasons(items: list[dict]) -> dict[str, str]:
    groups = {
        "structure": [],
        "expression": [],
        "readability": [],
        "tone": [],
        "value": [],
    }
    for item in items:
        if item["score"] >= item["max"]:
            continue
        key = item.get("key", "")
        line = f"{item['label']}: {item['comment']}"
        if key.startswith("structure_"):
            groups["structure"].append(line)
        elif key in {"lead", "clarity", "closing", "style_guide"}:
            groups["expression"].append(line)
        elif key.startswith("readability_"):
            groups["readability"].append(line)
        elif key == "tone":
            groups["tone"].append(line)
        else:
            groups["value"].append(line)
    return {k: "\n".join(v) if v else "없음" for k, v in groups.items()}


def _suggested_fix(items: list[dict]) -> str:
    weak = sorted(
        (it for it in items if it["score"] < it["max"]),
        key=lambda it: (it["score"] / it["max"] if it["max"] else 1),
    )
    if not weak:
        return "없음"
    lines = [
        f"- {it['label']}: {it['comment']}"
        for it in weak[:5]
    ]
    return "다음 항목을 우선 보완하세요.\n" + "\n".join(lines)


def _build_feedback(head: str, checklist: str, suggested_fix: str) -> str:
    # web.ui_theme.render_review_feedback() expects every line after the head
    # to match the checklist item format. suggested_fix is returned separately.
    return (head + checklist)[:990]


def _save_review(review: ReviewResult, status: str, revision_count: int) -> None:
    try:
        thread_id = (get_config().get("configurable") or {}).get("thread_id")
    except Exception:
        thread_id = None
    if not thread_id:
        return
    try:
        updated = execute(
            "UPDATE newsletter "
            "SET review_score = %s, review_feedback = %s, status = %s, revision_count = %s "
            "WHERE thread_id = %s",
            (review.get("score"), review.get("feedback"), status, revision_count, thread_id),
        )
        if not updated:
            print(f"[검수] 갱신된 보고서가 없습니다(thread_id={thread_id}).")
    except Exception as e:
        print(f"[검수] 점수 DB 저장 실패(무시하고 진행): {e}")
