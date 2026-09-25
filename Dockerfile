FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

# 先装依赖，利用层缓存
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用、前端与脚本
COPY app ./app
COPY frontend ./frontend
COPY scripts ./scripts
COPY pytest.ini ./pytest.ini
RUN chmod +x scripts/verify.sh

EXPOSE 8080

# 容器级健康检查（compose 另有 healthcheck 指向业务健康端点）
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import json,urllib.request,sys; r=urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8080')+'/healthz',timeout=3); sys.exit(0 if json.load(r)['status']=='ok' else 1)"

CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"
