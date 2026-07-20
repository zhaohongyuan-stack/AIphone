"""
市场监督管理局智能语音工单系统 - 启动入口
"""
import time

import uvicorn
from fastapi import FastAPI

from config import settings
from database.models import init_db, engine, AgentInfo, WorkOrder, DialogueDetail, SessionLocal
from database.init_robot_db import init_robot_agent_db
from api.routes import router
from core import redis_manager as rm
from core.aliyun_client import aliyun
from core.knowledge_base import kb
from core.rocketmq_consumer import start_consumer as start_mq_consumer
from core import logger as log


def _seed_agents(db):
    """若无坐席数据，自动初始化种子坐席（使用 CCC 控制台真实坐席账号）"""
    from core import redis_manager as rm

    if db.query(AgentInfo).count() > 0:
        return
    # CCC UserId 格式: 用户名@实例ID
    # 使用 CCC 控制台已存在的真实坐席账号，不能改用户名
    ccc_suffix = settings.CCC_INSTANCE_ID
    agents = [
        AgentInfo(agent_name="马宇航", agent_status=2,
                  ccc_agent_id=f"mayuhang@{ccc_suffix}"),
        AgentInfo(agent_name="nick", agent_status=2,
                  ccc_agent_id=f"nick4549741075@{ccc_suffix}"),
    ]
    db.add_all(agents)
    db.commit()
    # 同步 Redis 状态为 idle，确保启动后即可被转人工分配
    for a in agents:
        rm.set_agent_status(a.agent_id, "idle")
    log.info("已初始化 2 个种子坐席（CCC 真实账号，默认在线空闲）")


def check_services() -> tuple[bool, bool, bool, bool, int]:
    """启动时检查各服务连通性（生产模式：只建表，不删数据）"""
    pg_ok, redis_ok, aliyun_ok, robot_db_ok, agent_count = False, False, False, False, 0

    # PostgreSQL (ivr_system 主库 — RDS 云数据库)
    try:
        # 生产模式：仅创建不存在的表，不删除任何数据
        init_db(drop_existing=False)
        db = SessionLocal()
        _seed_agents(db)
        agent_count = db.query(AgentInfo).count()
        # 每次启动将所有 agent_status=2（在线）的坐席同步到 Redis 为 idle
        for a in db.query(AgentInfo).all():
            if a.agent_status == 2:
                rm.set_agent_status(a.agent_id, "idle")
        db.close()
        pg_ok = True
    except Exception as e:
        log.error(f"PostgreSQL (RDS) 连接失败: {e}")

    # PostgreSQL (robot_agent_db 智能坐席库 — 本地)
    try:
        robot_db_ok = init_robot_agent_db()
        if robot_db_ok:
            log.info("robot_agent_db 初始化成功")
        else:
            log.warning("robot_agent_db 初始化失败，智能坐席状态查询将降级为 Redis 数据")
    except Exception as e:
        log.error(f"robot_agent_db 初始化失败: {e}")

    # Redis
    try:
        rm.r.ping()
        # 清空内存队列和槽位（这些是运行态缓存，重启后必然需要重置）
        # 注意：不清除 ccc:event:* 去重标记，避免 RocketMQ 消息重复消费
        rm.r.delete(rm.QUEUE_KEY)
        for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
            rm.release_slot(i)
        redis_ok = True
    except Exception as e:
        log.error(f"Redis 连接失败: {e}")

    # 阿里云SDK
    try:
        if settings.ALIYUN_ACCESS_KEY_ID:
            aliyun_ok = True
    except Exception as e:
        log.error(f"阿里云SDK 初始化失败: {e}")

    return pg_ok, redis_ok, aliyun_ok, robot_db_ok, agent_count


app = FastAPI(
    title="市场监督管理局智能语音工单系统",
    description="IVR分流 + 智能机器人对话 + 人工兜底 + 工单流转",
    version="1.0.0",
)
app.include_router(router)


@app.on_event("startup")
def on_startup():
    # 在 worker 子进程中统一配置日志（reload=True 时 setup 在此生效）
    log.setup()
    log.banner()
    time.sleep(0.3)
    pg_ok, redis_ok, aliyun_ok, robot_db_ok, agent_count = check_services()
    log.startup_info(pg_ok, redis_ok, aliyun_ok,
                     settings.ROBOT_SLOT_COUNT, agent_count)
    if robot_db_ok:
        log.info("智能坐席状态库 (robot_agent_db): 已连接")
    else:
        log.info("智能坐席状态库 (robot_agent_db): 未连接（降级模式）")
    # 启动 RocketMQ 消费者（后台线程，消费 CCC 事件推送）
    start_mq_consumer()
    log.info(f"服务已启动: http://localhost:8000")
    log.info(f"API文档: http://localhost:8000/docs")
    log.info(f"知识库: 可回答 {len(kb.answerable)} 条, 拒绝解答 {len(kb.rejected)} 条")


@app.on_event("shutdown")
def on_shutdown():
    """关闭时清理资源"""
    from core.rocketmq_consumer import stop_consumer
    stop_consumer()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
