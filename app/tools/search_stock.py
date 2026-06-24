"""도구(Tool): 주가 조회 — @tool 데코레이터 (박희순_과제소스의 exchange_info 참고).

LLM이 종목 정보가 필요하다고 판단하면 종목코드(티커)로 호출합니다.
"""
from __future__ import annotations

from langchain_core.tools import tool

#테스트

@tool
def search_stock(symbol: str) -> str:
    """주식 종목코드(티커)로 현재 주가·등락 정보를 조회합니다.

    예) 애플=AAPL, 테슬라=TSLA, 삼성전자=005930.KS, SK하이닉스=000660.KS
    """
    print(f"\n[Tool 가동] search_stock -> {symbol}")
    import requests   # 도구가 쓰일 때만 불러옵니다

    symbol = symbol.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    try:
        resp = requests.get(
            url,
            params={"range": "1d", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        resp.raise_for_status()
        meta = resp.json()["chart"]["result"][0]["meta"]
    except Exception as e:   # 네트워크/잘못된 티커 등 → 안내 메시지로 폴백
        print(f"[search_stock] 조회 실패: {e}")
        return f"'{symbol}' 주가를 가져오지 못했습니다. (종목코드를 확인하거나 잠시 후 다시 시도)"

    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    currency = meta.get("currency", "")
    name = meta.get("longName") or meta.get("shortName") or symbol

    if price is None:
        return f"'{symbol}' 종목을 찾을 수 없습니다. 종목코드를 확인해 주세요."

    line = f"[{name} ({symbol})] 현재가 {price:,} {currency}"
    if prev:
        diff = price - prev
        rate = diff / prev * 100 if prev else 0
        sign = "▲" if diff > 0 else ("▼" if diff < 0 else "-")
        line += f" / 전일대비 {sign} {abs(diff):,.2f} ({rate:+.2f}%)"
    return line
