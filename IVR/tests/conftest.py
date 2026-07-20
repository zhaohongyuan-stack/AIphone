"""
pytest 配置：fixtures + 数据清理
- 不 mock 任何阿里云组件，CCC/Beebot 走真实 API
- 仅"事件通道"用假数据：CCC 事件通过 /api/ccc/callback 直接 POST（绕过 RocketMQ）
- 使用真实 PostgreSQL + Redis + LLM Skill + Beebot + CCC
- 每个测试前自动清理 PG 工单/对话 + Redis 缓存
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from config import settings


@pytest.fixture(scope="session")
def app_client():
    """
    创建 FastAPI 测试客户端（session 级别）
    - 不 patch aliyun，直接使用真实 core.aliyun_client.aliyun 单例
    - TestClient 触发 on_startup（初始化 DB、种子坐席、清空旧数据）
    - RocketMQ 未配置时不会启动消费者（CCC 事件通过 HTTP 接口直接 POST）
    """
    from main import app
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def clean_state(app_client):
    """
    每个测试前自动清理 PG + Redis 状态
    - PG: 清空 work_order + dialogue_detail，重置序列
    - Redis: 清空 queue、slot、history、pending、event
    - 保留 agent 状态（重置为 idle）
    """
    from database.models import SessionLocal, WorkOrder, DialogueDetail, AgentInfo
    from core import redis_manager as rm

    # ── 清理 PostgreSQL ──
    db = SessionLocal()
    db.query(DialogueDetail).delete()
    db.query(WorkOrder).delete()
    db.commit()
    db.execute(text("ALTER SEQUENCE IF EXISTS work_order_order_id_seq RESTART WITH 1"))
    db.execute(text("ALTER SEQUENCE IF EXISTS dialogue_detail_dia_id_seq RESTART WITH 1"))
    db.commit()
    # 重置机器人坐席状态为离线（SQLite robot_agent.db，表不存在时自动跳过）
    try:
        from database.robot_agent_db import get_connection
        conn = get_connection()
        conn.execute(
            "UPDATE robot_agent SET agent_status=0, contact_id=NULL, "
            "channel_id=NULL, call_type=NULL, ringing_slots=0, "
            "talking_slots=0, break_code=NULL, last_event=NULL, "
            "last_event_time=NULL, updated_time=datetime('now','localtime')"
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    # 重置坐席状态为 idle
    for a in db.query(AgentInfo).all():
        if a.agent_status == 1:
            rm.set_agent_status(a.agent_id, "idle")
    db.close()

    # ── 清理 Redis ──
    rm.r.delete(rm.QUEUE_KEY)
    rm.r.delete(rm.AGENT_QUEUE_KEY)  # 清空人工坐席队列
    for i in range(1, 10):
        rm.release_slot(i)
    for key in rm.r.scan_iter("history:*"):
        rm.r.delete(key)
    for key in rm.r.scan_iter("call:pending:*"):
        rm.r.delete(key)
    for key in rm.r.scan_iter("ccc:event:*"):
        rm.r.delete(key)

    yield


@pytest.fixture
def db_session():
    """获取数据库会话（测试中直接查询 DB 验证数据）"""
    from database.models import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def redis_client():
    """获取 Redis 客户端"""
    from core import redis_manager as rm
    return rm.r


@pytest.fixture
def aliyun_client():
    """
    获取真实 aliyun 客户端实例（用于直接调用 CCC/Beebot API）
    注意：CCC 需要 ALIYUN_ACCESS_KEY_ID + CCC_INSTANCE_ID
          Beebot 需要 ALIYUN_ACCESS_KEY_ID + BEEBOT_INSTANCE_ID
    未配置时 aliyun_client 内部会返回 SIMULATE 数据，不影响测试运行
    """
    from core.aliyun_client import aliyun
    return aliyun
