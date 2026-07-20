"""
Redis 管理：智能坐席槽位、排队队列、历史对话、坐席状态缓存
"""
import json
import time
from typing import Optional

import redis

from config import settings

r = redis.from_url(settings.redis_url, decode_responses=True)


# ═══════════════════════════════════════════════════════════════
#  智能坐席槽位
# ═══════════════════════════════════════════════════════════════

def _slot_key(slot_id: int) -> str:
    return f"robot:slot:{slot_id}"


def get_idle_slot() -> Optional[int]:
    """找一个空闲槽位，返回槽位号；没有则返回None"""
    for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
        data = r.get(_slot_key(i))
        if not data or json.loads(data).get("status") == "idle":
            return i
    return None


def occupy_slot(slot_id: int, order_id: int, session_id: str) -> bool:
    """占用槽位"""
    r.set(_slot_key(slot_id), json.dumps({
        "status": "busy",
        "order_id": order_id,
        "session_id": session_id,
        "started_at": time.time(),
    }, ensure_ascii=False))
    _sync_robot_agent_to_db(slot_id, 1, str(order_id))
    return True


def release_slot(slot_id: int) -> bool:
    """释放槽位"""
    r.set(_slot_key(slot_id), json.dumps({
        "status": "idle",
        "order_id": None,
        "session_id": None,
        "started_at": None,
    }, ensure_ascii=False))
    _sync_robot_agent_to_db(slot_id, 2)
    return True


def get_slot_status(slot_id: int) -> dict:
    """获取单个槽位状态"""
    data = r.get(_slot_key(slot_id))
    if not data:
        return {"slot_id": slot_id, "status": "idle",
                "order_id": None, "session_id": None, "started_at": None}
    info = json.loads(data)
    info["slot_id"] = slot_id
    if info.get("started_at"):
        info["duration_seconds"] = int(time.time() - info["started_at"])
    return info


def get_all_slots() -> list:
    """获取所有槽位状态"""
    return [get_slot_status(i) for i in range(1, settings.ROBOT_SLOT_COUNT + 1)]


def find_slot_by_order(order_id: int) -> Optional[int]:
    """根据工单ID找到对应槽位"""
    for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
        info = get_slot_status(i)
        if info.get("order_id") == order_id:
            return i
    return None


# ═══════════════════════════════════════════════════════════════
#  智能坐席排队队列 (FIFO)
# ═══════════════════════════════════════════════════════════════

QUEUE_KEY = "robot:queue"


def enqueue_robot(order_id: int, phone: str) -> int:
    """加入智能坐席排队队列，返回队列位置（从1开始）"""
    r.rpush(QUEUE_KEY, json.dumps({
        "order_id": order_id,
        "phone": phone,
        "joined_at": time.time(),
    }, ensure_ascii=False))
    return r.llen(QUEUE_KEY)


def dequeue_robot() -> Optional[dict]:
    """从队列取出下一个等待的用户"""
    data = r.lpop(QUEUE_KEY)
    return json.loads(data) if data else None


def get_queue_length() -> int:
    return r.llen(QUEUE_KEY)


# ═══════════════════════════════════════════════════════════════
#  历史对话 (JSON列表)
# ═══════════════════════════════════════════════════════════════

def _history_key(order_id: int) -> str:
    return f"history:{order_id}"


def append_history(order_id: int, role: str, content: str):
    """追加一条历史对话，限制最近20轮（40条）"""
    key = _history_key(order_id)
    r.rpush(key, json.dumps({
        "role": role,
        "content": content,
        "time": time.strftime("%H:%M:%S"),
    }, ensure_ascii=False))
    # 滑动窗口：保留最近40条
    r.ltrim(key, -40, -1)


def get_history(order_id: int) -> list:
    """获取历史对话列表"""
    items = r.lrange(_history_key(order_id), 0, -1)
    return [json.loads(item) for item in items]


def clear_history(order_id: int):
    r.delete(_history_key(order_id))


# ═══════════════════════════════════════════════════════════════
#  人工坐席状态缓存
# ═══════════════════════════════════════════════════════════════

def _agent_key(agent_id: int) -> str:
    return f"agent:{agent_id}:status"


def set_agent_status(agent_id: int, status: str):
    """status: idle / busy / offline"""
    r.set(_agent_key(agent_id), status)


def get_agent_status(agent_id: int) -> str:
    return r.get(_agent_key(agent_id)) or "offline"


def get_idle_agent() -> Optional[int]:
    """找一个空闲人工坐席ID（从agents表缓存中找）"""
    # 遍历所有 agent:*:status 键
    for key in r.scan_iter("agent:*:status"):
        if r.get(key) == "idle":
            agent_id = int(key.split(":")[1])
            return agent_id
    return None


# ═══════════════════════════════════════════════════════════════
#  人工坐席排队队列 (FIFO)
# ═══════════════════════════════════════════════════════════════

AGENT_QUEUE_KEY = "agent:queue"


def enqueue_agent(order_id: int, phone: str, ai_summary: str = "") -> int:
    """加入人工坐席排队队列，返回队列位置（从1开始）"""
    r.rpush(AGENT_QUEUE_KEY, json.dumps({
        "order_id": order_id,
        "phone": phone,
        "ai_summary": ai_summary,
        "joined_at": time.time(),
    }, ensure_ascii=False))
    return r.llen(AGENT_QUEUE_KEY)


def dequeue_agent() -> Optional[dict]:
    """从人工队列取出下一个等待的工单"""
    data = r.lpop(AGENT_QUEUE_KEY)
    return json.loads(data) if data else None


def get_agent_queue_length() -> int:
    return r.llen(AGENT_QUEUE_KEY)


def get_agent_queue_items() -> list:
    """获取人工队列所有等待项（不弹出）"""
    items = r.lrange(AGENT_QUEUE_KEY, 0, -1)
    return [json.loads(item) for item in items]


# ═══════════════════════════════════════════════════════════════
#  IVR 来电暂存（等待按键分流）
# ═══════════════════════════════════════════════════════════════

PENDING_CALL_TTL = 300  # 5分钟


def cache_pending_call(conv_id: str, phone: str, instance_id: str):
    """缓存来电信息，等待后续事件使用
    
    Args:
        conv_id: CCC 会话 ID (contactId)
        phone: 来电号码
        instance_id: CCC 实例 ID
    """
    r.set(f"call:pending:{conv_id}", json.dumps({
        "phone": phone,
        "instance_id": instance_id,
    }, ensure_ascii=False), ex=PENDING_CALL_TTL)


def get_pending_call(conv_id: str) -> Optional[dict]:
    """取出缓存的来电信息"""
    data = r.get(f"call:pending:{conv_id}")
    return json.loads(data) if data else None


def clear_pending_call(conv_id: str):
    """清除来电缓存"""
    r.delete(f"call:pending:{conv_id}")


# ═══════════════════════════════════════════════════════════════
# CCC 事件回调幂等去重
# ═══════════════════════════════════════════════════════════════

EVENT_KEY_PREFIX = "ccc:event"
EVENT_TTL = 3600  # 1小时


def set_event_processed(event_id: str) -> bool:
    """
    标记事件已处理（幂等去重）
    返回 True 表示首次处理，False 表示重复事件应跳过
    """
    if not event_id:
        return True
    key = f"{EVENT_KEY_PREFIX}:{event_id}"
    # SET NX: 仅当 key 不存在时设置
    return r.set(key, "1", nx=True, ex=EVENT_TTL)


def is_event_processed(event_id: str) -> bool:
    """检查事件是否已处理过"""
    if not event_id:
        return False
    return r.exists(f"{EVENT_KEY_PREFIX}:{event_id}") > 0


# ═══════════════════════════════════════════════════════════════
#  DB 同步：机器人坐席状态写入 PostgreSQL
# ═══════════════════════════════════════════════════════════════

def _sync_robot_agent_to_db(slot_id: int, status: int, contact_id: str = None):
    """
    将机器人坐席槽位状态同步到 SQLite robot_agent 表
    status: 0=离线, 1=忙碌, 2=在线空闲
    同步失败不影响主流程（仅日志记录）
    """
    try:
        from database.robot_agent_db import get_connection, robot_agent_update_by_slot
        conn = get_connection()
        robot_agent_update_by_slot(conn, slot_id, status, contact_id)
        conn.close()
    except Exception:
        # DB 同步失败不影响 Redis 主流程（表未创建/无记录时静默跳过）
        pass


# ═══════════════════════════════════════════════════════════════
#  robot_agent_db 查询接口（供 /api/robot-slots/status 使用）
# ═══════════════════════════════════════════════════════════════

def _robot_db_connect():
    """获取 robot_agent.db 的 sqlite3 连接（调用方负责 close）"""
    from database.robot_agent_db import get_connection
    return get_connection()


# agent_status → system_status 映射
_STATUS_MAP = {0: "offline", 1: "busy", 2: "online"}

# agent_status → health_status 映射
_HEALTH_MAP = {0: "unknown", 1: "healthy", 2: "healthy"}


def query_robot_agents_detail() -> list:
    """
    从 SQLite robot_agent.db 查询所有机器人坐席的详细状态
    合并 Redis 实时槽位数据（session_id / order_id / started_at）与 DB 持久化数据
    返回接口文档要求的 robot_agents[] 格式
    """
    import time as _time
    from datetime import datetime as _dt

    # 先从 Redis 取实时槽位数据（session_id / order_id / started_at 是 Redis 实时维护的）
    redis_slots = {}
    for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
        slot_info = get_slot_status(i)
        redis_slots[i] = slot_info

    result = []
    try:
        from database.robot_agent_db import get_connection
        conn = get_connection()
        cur = conn.execute(
            "SELECT id, agent_name, agent_status, slot_id, "
            "ccc_agent_id, skill_group_id, max_slots, "
            "contact_id, last_event, last_event_time, "
            "check_in_time, updated_time "
            "FROM robot_agent ORDER BY slot_id"
        )
        rows = cur.fetchall()
        conn.close()

        for row in rows:
            (db_id, agent_name, agent_status, slot_id,
             ccc_agent_id, skill_group_id, max_slots,
             contact_id, last_event, last_event_time,
             check_in_time, updated_time) = row

            slot_info = redis_slots.get(slot_id, {})
            is_busy = slot_info.get("status") == "busy"
            current_order_id = slot_info.get("order_id")
            session_id = slot_info.get("session_id")
            started_at = slot_info.get("started_at")

            # system_status: maintenance 优先（DB 中 agent_status=0 但有手动维护标记时）
            system_status = _STATUS_MAP.get(agent_status, "offline")
            if agent_status == 0 and last_event == "MaintenanceMode":
                system_status = "maintenance"

            # slot_status: 以 Redis 实时状态为准
            slot_status = "busy" if is_busy else ("idle" if agent_status == 2 else "offline")

            # health_status: 最近30秒内有事件 → healthy，否则需心跳判定
            health_status = _HEALTH_MAP.get(agent_status, "unknown")

            duration_seconds = None
            if started_at:
                duration_seconds = int(_time.time() - started_at)
            elif check_in_time:
                try:
                    check_dt = _dt.fromisoformat(check_in_time)
                    duration_seconds = int((_dt.now() - check_dt).total_seconds())
                except Exception:
                    pass

            # 心跳时间（SQLite 存的是 ISO 8601 字符串）
            last_heartbeat = None
            if last_event_time:
                last_heartbeat = last_event_time
            elif updated_time:
                last_heartbeat = updated_time

            result.append({
                "slot_id": slot_id,
                "robot_agent_id": f"robot_agent_{slot_id:02d}",
                "agent_name": agent_name,
                "system_status": system_status,
                "health_status": health_status,
                "slot_status": slot_status,
                "current_order_id": current_order_id,
                "session_id": session_id,
                "started_at": started_at if started_at else None,
                "duration_seconds": duration_seconds,
                "last_heartbeat": last_heartbeat,
            })
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"query_robot_agents_detail 失败，降级为 Redis 数据: {e}")
        # 降级：仅返回 Redis 数据
        for i in range(1, settings.ROBOT_SLOT_COUNT + 1):
            slot_info = redis_slots.get(i, {})
            is_busy = slot_info.get("status") == "busy"
            result.append({
                "slot_id": i,
                "robot_agent_id": f"robot_agent_{i:02d}",
                "agent_name": f"智能坐席{chr(64 + i)}",
                "system_status": "online",
                "health_status": "unknown",
                "slot_status": "busy" if is_busy else "idle",
                "current_order_id": slot_info.get("order_id"),
                "session_id": slot_info.get("session_id"),
                "started_at": slot_info.get("started_at"),
                "duration_seconds": int(_time.time() - slot_info["started_at"]) if slot_info.get("started_at") else None,
                "last_heartbeat": None,
            })

    return result


def update_robot_agent_system_status(slot_id: int, system_status: str,
                                     reason: str = "", operator_id: str = "") -> dict:
    """
    手动更新机器人坐席的系统级状态
    system_status: online / offline / maintenance
    """
    status_map = {"online": 2, "offline": 0, "maintenance": 0}
    db_status = status_map.get(system_status, 0)

    try:
        from database.robot_agent_db import get_connection, robot_agent_update_by_slot
        conn = get_connection()

        # 查询前状态
        cur = conn.execute("SELECT agent_status FROM robot_agent WHERE slot_id = ?", (slot_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": f"槽位 {slot_id} 不存在"}
        previous_status = _STATUS_MAP.get(row[0], "offline")

        if system_status == "maintenance":
            # 维护模式：设为离线，并标记 last_event 为 MaintenanceMode
            from datetime import datetime
            now = datetime.now().isoformat()
            conn.execute(
                "UPDATE robot_agent SET agent_status=0, last_event='MaintenanceMode', "
                "last_event_time=?, updated_time=? WHERE slot_id=?",
                (now, now, slot_id)
            )
            conn.commit()
        else:
            robot_agent_update_by_slot(conn, slot_id, db_status)
        conn.close()

        return {
            "success": True,
            "previous_status": previous_status,
            "current_status": system_status,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def update_robot_agent_heartbeat(slot_id: int, health_status: str,
                                current_load: float = None,
                                avg_response_time_ms: int = None) -> dict:
    """
    心跳上报：更新 health_status 和负载信息
    health_status: healthy / error / unknown
    如果超过30秒未收到心跳，系统自动标记为 error（由调用方或定时任务判定）
    """
    try:
        from database.robot_agent_db import get_connection
        from datetime import datetime
        conn = get_connection()
        now = datetime.now().isoformat()

        # 更新 last_event_time 为当前时间（心跳时间戳）
        cur = conn.execute(
            "UPDATE robot_agent SET last_event='Heartbeat', "
            "last_event_time=?, updated_time=? WHERE slot_id=? "
            "RETURNING id, agent_name, agent_status",
            (now, now, slot_id)
        )
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": f"槽位 {slot_id} 不存在"}

        db_id, agent_name, agent_status = row
        conn.close()

        return {
            "success": True,
            "slot_id": slot_id,
            "agent_name": agent_name,
            "health_status": health_status,
            "current_load": current_load,
            "avg_response_time_ms": avg_response_time_ms,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}
