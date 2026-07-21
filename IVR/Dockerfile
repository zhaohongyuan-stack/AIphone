# ==================== Python IVR 服务 Dockerfile ====================
# 基于 python:3.10-slim，安装依赖后运行 uvicorn

FROM python:3.10-slim

WORKDIR /app

# 使用阿里云 Debian 镜像源（加速国内 ECS 下载）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null || true

# 安装系统依赖（psycopg2-binary 自带 libpq，不需要 gcc 编译）
# 仅安装 libpq-dev 供 psycopg2-binary 运行时动态链接
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

# 先复制 requirements 利用 Docker 缓存
COPY requirements.txt .
# 使用阿里云 pip 镜像源加速
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

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
