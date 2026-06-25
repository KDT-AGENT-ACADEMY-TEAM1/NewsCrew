#!/usr/bin/env bash
set -Eeuo pipefail

export API_HOST="${API_HOST:-0.0.0.0}"
export API_PORT="${API_PORT:-8000}"
export API_BASE="${API_BASE:-http://127.0.0.1:8000}"
export STREAMLIT_SERVER_ADDRESS="${STREAMLIT_SERVER_ADDRESS:-0.0.0.0}"
export STREAMLIT_SERVER_PORT="${STREAMLIT_SERVER_PORT:-8501}"

python run_api.py &
API_PID="$!"

streamlit run web/streamlit_app.py \
  --server.address "$STREAMLIT_SERVER_ADDRESS" \
  --server.port "$STREAMLIT_SERVER_PORT" &
WEB_PID="$!"

shutdown() {
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
  wait "$API_PID" "$WEB_PID" 2>/dev/null || true
}

trap shutdown INT TERM EXIT

wait -n "$API_PID" "$WEB_PID"
EXIT_CODE="$?"
shutdown
exit "$EXIT_CODE"
