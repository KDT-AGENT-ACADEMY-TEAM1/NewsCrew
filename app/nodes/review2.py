from __future__ import annotations

import json
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI  # 혹은 사용하는 LLM 컴포넌트
from langgraph.config import get_config

from ..db import execute
from ..state import NewsletterState, ReviewResult

# LLM 초기화 (예시: GPT-4o 등 추론 능력이 좋은 모델 추천)
llm = ChatOpenAI(model="gpt-4o", temperature=0.2)

# ==========================================================================
# STEP 4. 검수 노드 — 초안 품질 판정 + 점수 저장
# ==========================================================================
def review_node(state: NewsletterState) -> NewsletterState:
    draft = state.get("draft", "")
    revision = state.get("revision_count", 0)
    print(f"[검수] AI 품질 검증 시작 ({revision}회차)")

    # 1. 단순 규칙 기반 대신 LLM 기반 검수 수행
    review = _llm_review(draft)
    
    revision_count = revision + 1
    # 통과하면 사람 승인 대기(interrupt), 실패하면 다시 작성(writing) 노드로 분기하기 위한 상태 설정
    status = "awaiting_approval" if review["passed"] else "writing"

    print(f"[검수] 결과: {'통과' if review['passed'] else '미달'} (점수: {review['score']})")
    
    # 2. DB에 검수 결과 반영
    _save_review(review, status, revision_count)   
    
    return {
        "review": review,
        "revision_count": revision_count,
        "status": status,
        "human_feedback": "",  # 이전 차수의 피드백은 초기화
    }


def _llm_review(draft: str) -> ReviewResult:
    """LLM을 사용하여 뉴스레터의 가독성, 흥미성, 형식을 종합 평가합니다."""
    if not draft or len(draft.strip()) < 100:
        return {"passed": False, "score": 30, "feedback": "초안의 분량이 너무 적거나 내용이 비어 있습니다."}

    system_prompt = (
        "당신은 뉴스레터 편집장입니다. 제공된 초안의 품질을 엄격히 심사해야 합니다.\n"
        "다음 3가지 기준을 바탕으로 평가해주세요:\n"
        "1. 가독성 및 구성: 소제목(##) 활용 및 문단 나누기가 잘 되어 있는가?\n"
        "2. 톤앤매너: 독자에게 친근하고 전문적인 어조를 유지하는가?\n"
        "3. 정보의 가치: 핵심 내용이 명확하고 흥미로운가?\n\n"
        "반드시 아래 JSON 포맷으로만 답변하세요. 다른 말은 하지 마세요.\n"
        "{\n"
        '  "passed": true 또는 false (종합 점수가 80점 이상이면 true),\n'
        '  "score": 0~100 사이의 정수 점수,\n'
        '  "feedback": "탈락했다면 구체적으로 어떤 점을 수정해야 하는지 피드백을, 통과했다면 칭찬 및 보완점 작성"\n'
        "}"
    )

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"--- 뉴스레터 초안 ---\n{draft}")
        ])
        
        # JSON 파싱 (안전장치 포함)
        result = json.loads(response.content.strip().replace("```json", "").replace("```", ""))
        
        # 타입 검증 및 기본값 보장
        return {
            "passed": bool(result.get("passed", False)),
            "score": int(result.get("score", 0)),
            "feedback": str(result.get("feedback", "평가 결과가 올바르지 않습니다."))
        }
    except Exception as e:
        print(f"[검수 에러] LLM 검수 중 오류 발생: {e}")
        # LLM 장애 시 시스템이 멈추지 않도록 Fail-Safe 처리 (재작성 유도)
        return {
            "passed": False,
            "score": 50,
            "feedback": f"AI 검수 프로세스 오류로 인해 재작성을 요청합니다. (에러: {e})"
        }


def _save_review(review: ReviewResult, status: str, revision_count: int) -> None:
    """검수 점수/코멘트/상태를 newsletter 테이블에 갱신합니다."""
    try:
        thread_id = (get_config().get("configurable") or {}).get("thread_id")
    except Exception:
        thread_id = None
        
    if not thread_id:
        print("[검수] thread_id를 찾을 수 없어 DB 저장을 건너뜁니다.")
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