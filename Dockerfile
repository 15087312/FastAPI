# 多阶段构建 - 生产环境镜像
FROM python:3.11-slim as base

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ============================================
# 开发阶段
# ============================================
FROM base AS development

# 复制项目代码
COPY . .

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["python", "app/main.py"]

# ============================================
# 生产环境优化
# ============================================
FROM base AS production

# 创建非 root 用户
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# 复制项目代码
COPY . .

# 更改文件所有权
RUN chown -R appuser:appgroup /app

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 生产环境启动命令：使用 Gunicorn + Uvicorn workers
# -k uvicorn.workers.UvicornWorker: 使用 Uvicorn worker
# -w 8: 8 个 worker 进程
# --worker-connections 2000: 每个 worker 最大连接数，避免 socket 堵塞
# -b 0.0.0.0:8000: 监听地址
# --timeout 60: 请求超时时间
# --keep-alive 5: keep-alive 超时时间
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "8", "--worker-connections", "2000", "-b", "0.0.0.0:8000", "--timeout", "60", "--keep-alive", "5"]
