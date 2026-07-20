"""
DB 同事脚本 1/3：初始化测试数据
- 清理旧数据（工单、对话明细、坐席）
- 创建测试坐席
- 初始化 Redis 槽位为 idle

用法:
    python -m database.seed_data           # 清理 + 初始化
    python -m database.seed_data --check   # 仅查看当前状态
"""
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import WorkOrder, DialogueDetail, AgentInfo, SessionLocal, init_db
from database.init_robot_db import init_robot_agent_db
from core import redis_manager as rm
from config import settings

import redis


# ⚠️ 需要替换为你 CCC 控制台中的真实坐席账号
# 格式: ccc_agent_id = "坐席用户名@CCC实例ID"
# 在 CCC 控制台 → 坐席管理 → 坐席列表中查看
# 如果不知道坐席用户名，可以先在 CCC 控制台创建坐席
# 示例: 如果你的 CCC 实例 ID 是 demo-1334882287961657，坐席用户名是 zhangsan
#       则 ccc_agent_id = "zhangsan@demo-1334882287961657"
TEST_AGENTS = [
    {
        "agent_name": "坐席1",
        "agent_status": 2,  # 在线
        "ccc_agent_id": "agent_b",  # ← 替换
    },
    {
        "agent_name": "坐席2",
        "agent_status": 2,  # 在线
        "ccc_agent_id": "mayuhang",  # ← 替换
    },
]


def check_status():
    """查看当前数据库和 Redis 状态"""
    db = SessionLocal()
    try:
        order_count = db.query(WorkOrder).count()
        dialogue_count = db.query(DialogueDetail).count()
        agent_count = db.query(AgentInfo).count()
        slots = rm.get_all_slots()
        queue_len = rm.get_queue_length()

        print("=" * 50)
        print("当前状态")
        print("=" * 50)
        print(f"  工单数:       {order_count}")
        print(f"  对话明细数:   {dialogue_count}")
        print(f"  坐席数:       {agent_count}")
        print(f"  槽位状态:     {len(slots)} 个")
        for s in slots:
            status = s.get("status", "idle")
            oid = s.get("order_id")
            print(f"    Slot#{s['slot_id']}: {status}"
                  + (f" (工单#{oid})" if oid else ""))
        print(f"  排队队列:     {queue_len} 人")
        print("=" * 50)
    finally:
        db.close()


def clean_all():
    """清理所有测试数据"""
    db = SessionLocal()
    try:
        deleted_dialogue = db.query(DialogueDetail).delete()
        deleted_orders = db.query(WorkOrder).delete()
        deleted_agents = db.query(AgentInfo).delete()
        db.commit()
        print(f"已清理: 工单 {deleted_orders} 条, "
              f"对话明细 {deleted_dialogue} 条, "
              f"坐席 {deleted_agents} 条")
    finally:
        db.close()

    # 清理 Redis
    r = redis.from_url(settings.redis_url, decode_responses=True)
    # 清理槽位
    for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
        r.delete(f"robot:slot:{i}")
    # 清理队列
    r.delete("robot:queue")
    # 清理历史对话
    for key in r.scan_iter("history:*"):
        r.delete(key)
    # 清理来电缓存
    for key in r.scan_iter("call:pending:*"):
        r.delete(key)
    # 清理事件去重
    for key in r.scan_iter("ccc:event:*"):
        r.delete(key)
    # 清理坐席状态缓存
    for key in r.scan_iter("agent:*:status"):
        r.delete(key)
    print("已清理 Redis: 槽位、队列、历史对话、来电缓存、事件去重、坐席状态")


def seed_agents():
    """创建测试坐席"""
    db = SessionLocal()
    try:
        for agent_data in TEST_AGENTS:
            agent = AgentInfo(**agent_data)
            db.add(agent)
            db.commit()
            db.refresh(agent)
            # 缓存坐席状态到 Redis
            status_map = {0: "offline", 1: "busy", 2: "idle"}
            rm.set_agent_status(agent.agent_id, status_map[agent.agent_status])
            print(f"  创建坐席: {agent.agent_name} (ID={agent.agent_id}, "
                  f"状态={status_map[agent.agent_status]})")
    finally:
        db.close()


def init_slots():
    """初始化所有槽位为 idle"""
    # 先确保 robot_agent_db 已建表和初始化
    init_robot_agent_db()
    for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
        rm.release_slot(i)
    print(f"已初始化 {settings.ROBOT_SLOT_COUNT} 个槽位为 idle")


def _init_robot_agent_table():
    """初始化 robot_agent 表（独立数据库，UPSERT：已存在则跳过）"""
    import psycopg2
    try:
        conn = psycopg2.connect(settings.robot_db_url)
        conn.autocommit = True
        cur = conn.cursor()
        for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
            cur.execute("SELECT 1 FROM robot_agent WHERE slot_id = %s", (i,))
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO robot_agent (agent_name, agent_status, slot_id, max_slots) "
                    "VALUES (%s, 0, %s, 10)",
                    (f"机器人坐席-{i}", i)
                )
        cur.close()
        conn.close()
        print(f"已初始化 {settings.ROBOT_SLOT_COUNT} 个 robot_agent 记录")
    except Exception as e:
        print(f"robot_agent 表初始化失败（可能库/表未创建）: {e}")


def main():
    if "--check" in sys.argv:
        # 仅查看状态，不建表、不清数据
        check_status()
        return

    # 确保表已创建（含旧表清理）
    init_db()
    print("开始初始化测试数据...")
    clean_all()
    print("创建测试坐席...")
    seed_agents()
    init_slots()
    print("\n初始化完成！当前状态:")
    check_status()


if __name__ == "__main__":
    main()
