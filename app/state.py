"""그래프가 공유하는 '상태(State)' 정의 — 학습용 심플 버전.

[상태]란?
  리서치 → 작성 → 검수 → 발송으로 이어지는 각 단계가 주고받는 '공용 메모지'입니다.
  한 단계가 결과를 메모지에 적어 두면, 다음 단계가 그 메모지를 읽어 일을 이어 갑니다.

TypedDict 란?
  그냥 dict(딕셔너리)인데, "어떤 키에 어떤 타입이 들어오는지" 미리 적어 두는 것입니다.
  실행에는 영향이 없고, 코드를 읽을 때/자동완성할 때 도움이 됩니다.
"""
from __future__ import annotations

from typing import TypedDict


# --------------------------------------------------------------------------
# 검수 결과 한 덩어리 (검수 에이전트가 만들어 채웁니다)
# --------------------------------------------------------------------------
class ReviewResult(TypedDict):
    passed: bool      # 품질 통과 여부 (True=통과 / False=미달 → 다시 작성)
    score: int        # 0~100 점수
    feedback: str     # 수정 요청 사유 또는 통과 코멘트


# --------------------------------------------------------------------------
# 파이프라인 전체가 공유하는 메모지
#   total=False  →  모든 키를 처음부터 다 채울 필요는 없다는 뜻
#                   (각 단계가 자기 차례에 필요한 항목만 채워 갑니다)
# --------------------------------------------------------------------------
class NewsletterState(TypedDict, total=False):
    # 1) 사용자 입력
    keywords: list[str]        # 관심 키워드 (예: ["전기차", "배터리"])

    # 2~4) 각 에이전트가 채우는 결과
    research: str              # [리서치] 수집·정리한 자료
    draft: str                 # [작성]   뉴스레터 초안 (마크다운)
    review: ReviewResult       # [검수]   품질 판정 결과

    # 작성 <-> 검수 루프 제어
    revision_count: int        # 지금까지 작성/재작성을 몇 번 했는지
    max_revisions: int         # 최대 몇 번까지 다시 쓸지 (무한 루프 방지)
    human_feedback: str        # 사람이 '반려'할 때 남기는 추가 요청

    # 진행 상태 / 최종 결과
    status: str                # researching | writing | reviewing | awaiting_approval | sent
    final: str                 # 최종 발송 본문

    # TODO: 항목을 더 넣고 싶으면 여기 추가하세요.
    #   예) sources: list[str]   # 리서치 출처 링크
    #   예) sent_at: str         # 발송 시각
