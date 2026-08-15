FROM python:3.12-slim

# mem0ai 依赖（可选，无则降级 json 记忆后端）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 层缓存）
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .[memory] psycopg2-binary

# 数据目录（运行时用 volume 挂载持久化）
ENV DHUB_ROOT=/opt/d-hub \
    DHUB_PORT=10101 \
    DHUB_HOST=0.0.0.0

VOLUME ["/opt/d-hub"]

EXPOSE 10101

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10101/health', timeout=3)" || exit 1

CMD ["python3", "-m", "dhub"]
