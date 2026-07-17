#!/bin/bash
# ================================================================
# AIPhone 一键部署脚本（阿里云 ECS）
# 公网地址：8.152.96.62
# 使用方式：在 ECS 上执行 bash deploy.sh
# ================================================================

set -e  # 遇错即停

# ==================== 配置区 ====================
APP_DIR="/opt/aiphone"              # 部署目录
LOG_FILE="/var/log/aiphone-deploy.log"  # 部署日志
COMPOSE_FILE="docker-compose-prod.yml"
PORT=8080

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%H:%M:%S')] [WARN]${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%H:%M:%S')] [ERROR]${NC} $1"
    exit 1
}

# ==================== 步骤 1：环境检查 ====================
log "==================== 步骤 1/6：环境检查 ===================="

# 检查 Docker
if ! command -v docker &> /dev/null; then
    error "Docker 未安装，请先安装 Docker"
fi
log "Docker 已安装：$(docker --version)"

# 检查 Docker Compose
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
else
    error "Docker Compose 未安装，请先安装"
fi
log "Docker Compose 可用：$COMPOSE_CMD"

# 检查 Docker 守护进程
if ! docker info &> /dev/null; then
    error "Docker 守护进程未运行，请执行 systemctl start docker"
fi
log "Docker 守护进程运行中"

# 检查端口占用
if ss -tlnp | grep -q ":$PORT "; then
    warn "端口 $PORT 已被占用，将先停止旧容器"
fi

# ==================== 步骤 2：准备部署目录 ====================
log "==================== 步骤 2/6：准备部署目录 ===================="

mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/logs"

# 复制部署文件到 /opt/aiphone（假设脚本在项目根目录执行）
log "复制部署文件到 $APP_DIR"
cp Dockerfile "$APP_DIR/" 2>/dev/null || warn "Dockerfile 不存在"
cp docker-compose-prod.yml "$APP_DIR/" 2>/dev/null || warn "docker-compose-prod.yml 不存在"
cp -r src "$APP_DIR/" 2>/dev/null || warn "src 目录不存在"
cp pom.xml "$APP_DIR/" 2>/dev/null || warn "pom.xml 不存在"

# 复制测试前端（如果有）
if [ -d "../test-frontend" ]; then
    mkdir -p "$APP_DIR/../test-frontend"
    cp -r ../test-frontend/* "$APP_DIR/../test-frontend/" 2>/dev/null
    log "测试前端已复制"
fi

cd "$APP_DIR"
log "当前目录：$(pwd)"

# ==================== 步骤 3：停止旧服务 ====================
log "==================== 步骤 3/6：停止旧服务 ===================="

if [ -f "$COMPOSE_FILE" ]; then
    $COMPOSE_CMD -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null && log "旧服务已停止" || log "无旧服务需要停止"
else
    log "无 compose 文件，跳过停止"
fi

# 清理旧镜像（可选，释放磁盘）
docker image prune -f 2>/dev/null || warn "清理旧镜像失败（可忽略）"

# ==================== 步骤 4：构建并启动 ====================
log "==================== 步骤 4/6：构建并启动服务 ===================="

log "开始构建镜像（首次构建约 5-10 分钟，依赖下载较多）..."
$COMPOSE_CMD -f "$COMPOSE_FILE" up -d --build

# 等待服务启动
log "等待服务启动..."
sleep 10

# ==================== 步骤 5：健康检查 ====================
log "==================== 步骤 5/6：健康检查 ===================="

MAX_RETRY=30
RETRY=0
HEALTHY=false

while [ $RETRY -lt $MAX_RETRY ]; do
    RETRY=$((RETRY + 1))

    # 检查容器状态
    APP_STATUS=$(docker inspect --format='{{.State.Status}}' aiphone-app 2>/dev/null || echo "not_found")
    REDIS_STATUS=$(docker inspect --format='{{.State.Status}}' aiphone-redis 2>/dev/null || echo "not_found")

    log "[$RETRY/$MAX_RETRY] app=$APP_STATUS, redis=$REDIS_STATUS"

    if [ "$APP_STATUS" = "running" ] && [ "$REDIS_STATUS" = "running" ]; then
        # 检查应用健康接口
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$PORT/actuator/health 2>/dev/null || echo "000")
        if [ "$HTTP_CODE" = "200" ]; then
            HEALTHY=true
            log "应用健康检查通过（HTTP $HTTP_CODE）"
            break
        else
            log "应用尚未就绪（HTTP $HTTP_CODE），等待重试..."
        fi
    fi

    sleep 5
done

if [ "$HEALTHY" = false ]; then
    error "应用启动失败，请查看日志：docker logs aiphone-app"
fi

# ==================== 步骤 6：部署完成 ====================
log "==================== 步骤 6/6：部署完成 ===================="

log "========================================"
log "  AIPhone 部署成功！"
log "========================================"
log ""
log "访问地址：http://8.152.96.62:$PORT"
log "健康检查：http://8.152.96.62:$PORT/actuator/health"
log "测试前端：http://8.152.96.62:$PORT/static/index.html"
log ""
log "常用命令："
log "  查看日志：docker logs -f aiphone-app"
log "  查看状态：docker ps"
log "  重启服务：$COMPOSE_CMD -f $COMPOSE_FILE restart"
log "  停止服务：$COMPOSE_CMD -f $COMPOSE_FILE down"
log "  重新部署：bash deploy.sh"
log ""
log "日志文件：$APP_DIR/logs/aiphone.log"
log "========================================"
