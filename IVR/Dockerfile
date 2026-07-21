# ==================== Python IVR 服务 Dockerfile ====================
# 基于 python:3.10-slim，安装依赖后运行 uvicorn

FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖（psycopg2-binary 需要 libpq，openpyxl 无额外依赖）
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# 先复制 requirements 利用 Docker 缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录（SQLite + 知识库挂载点）
RUN mkdir -p /app/data

# 时区
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

EXPOSE 8000

# 启动命令（通过 .env.docker 注入配置）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
