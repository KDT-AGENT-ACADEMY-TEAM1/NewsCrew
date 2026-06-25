FROM python:3.11.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y \
    bash \
    build-essential \
    curl \
    default-mysql-client \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.docker.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY web/ ./web/
COPY data/ ./data/
COPY .streamlit/ ./.streamlit/
COPY prompts.yaml ./
COPY run.py ./
COPY run_api.py ./
COPY schema.sql ./

COPY start.sh ./
RUN chmod +x start.sh

EXPOSE 8000
EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["./start.sh"]
