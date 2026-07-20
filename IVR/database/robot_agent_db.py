"""
智能坐席状态数据库（SQLite）
替代原来的 PostgreSQL robot_agent_db，提供：
- 建表 DDL（与 PostgreSQL 版本字段兼容）
- 8 个业务函数（替代 PL/pgSQL）
- 2 个视图查询（Python 实现）
- 连接管理

使用方式：
    from database.robot_agent_db import get_connection, init_robot_agents, robot_agent_update_by_slot
    conn = get_connection()
    init_robot_agents(conn, 2)
    robot_agent_update_by_slot(conn, 1, 1, "order-123")
    conn.close()
"""
import sqlite3
import threading
from datetime import datetime
from typing import Optional

from config import settings

# 线程本地存储
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    """
    获取 SQLite 连接（自动开启 WAL 模式）
    调用方负责 close()
    """
    conn = sqlite3.connect(settings.robot_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ═══════════════════════════════════════════════════════════════
#  DDL
# ═══════════════════════════════════════════════════════════════

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS robot_agent (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name        TEXT    NOT NULL,
    agent_status      INTEGER NOT NULL DEFAULT 0,
    slot_id           INTEGER NOT NULL,
    ccc_agent_id      TEXT,
    skill_group_id    TEXT,
    skill_level       INTEGER DEFAULT 5,
    work_mode         TEXT    DEFAULT 'ON_SITE',
    device_id         TEXT,
    chat_device_id    TEXT,
    max_slots         INTEGER DEFAULT 10,
    outbound_scenario INTEGER DEFAULT 0,
    break_code        TEXT,
    contact_id        TEXT,
    channel_id        TEXT,
    call_type         TEXT,
    ringing_slots     INTEGER DEFAULT 0,
    talking_slots     INTEGER DEFAULT 0,
    last_event        TEXT,
    last_event_time   TEXT,
    check_in_time     TEXT,
    created_time      TEXT    DEFAULT (datetime('now','localtime')),
    updated_time      TEXT    DEFAULT (datetime('now','localtime'))
)
"""

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_robot_agent_status  ON robot_agent (agent_status)",
    "CREATE INDEX IF NOT EXISTS idx_robot_agent_slot_id ON robot_agent (slot_id)",
    "CREATE INDEX IF NOT EXISTS idx_robot_agent_ccc_id  ON robot_agent (ccc_agent_id)",
]


def create_tables(conn: sqlite3.Connection):
    """建表 + 索引"""
    conn.execute(CREATE_TABLE_SQL)
    for sql in CREATE_INDEXES_SQL:
        conn.execute(sql)
    conn.commit()


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now().isoformat()


# ═══════════════════════════════════════════════════════════════
#  1. 初始化机器人坐席
# ═══════════════════════════════════════════════════════════════

def init_robot_agents(conn: sqlite3.Connection, slot_count: int = 3) -> list:
    """创建指定数量的机器人坐席记录，已存在的 slot_id 跳过"""
    results = []
    for i in range(1, slot_count + 1):
        cur = conn.execute("SELECT 1 FROM robot_agent WHERE slot_id = ?", (i,))
        if cur.fetchone():
            continue
        cur = conn.execute(
            "INSERT INTO robot_agent (agent_name, agent_status, slot_id, max_slots) "
            "VALUES (?, 0, ?, 10)",
            (f"机器人坐席-{i}", i)
        )
        new_id = cur.lastrowid
        results.append((new_id, f"机器人坐席-{i}", i))
    conn.commit()
    return results


# ═══════════════════════════════════════════════════════════════
#  2. 坐席签入 (AgentCheckIn)
# ═══════════════════════════════════════════════════════════════

def robot_agent_check_in(
    conn: sqlite3.Connection, ccc_agent_id: str,
    skill_group_id: Optional[str] = None, skill_level: int = 5,
    work_mode: str = "ON_SITE", device_id: Optional[str] = None,
    chat_device_id: Optional[str] = None, max_slots: int = 10,
) -> tuple:
    """坐席签入，返回 (id, status, msg)"""
    cur = conn.execute("SELECT * FROM robot_agent WHERE ccc_agent_id = ?", (ccc_agent_id,))
    row = cur.fetchone()

    if not row:
        cur = conn.execute(
            "SELECT * FROM robot_agent WHERE ccc_agent_id IS NULL AND agent_status=0 "
            "ORDER BY slot_id LIMIT 1"
        )
        row = cur.fetchone()
        if not row:
            return (0, 0, "无可用槽位，请先初始化机器人坐席")

    now = _now()
    conn.execute(
        "UPDATE robot_agent SET agent_status=2, ccc_agent_id=?, skill_group_id=?, "
        "skill_level=?, work_mode=?, device_id=?, chat_device_id=?, max_slots=?, "
        "last_event='AgentCheckIn', last_event_time=?, check_in_time=?, updated_time=? "
        "WHERE id=?",
        (ccc_agent_id, skill_group_id or row["skill_group_id"], skill_level,
         work_mode, device_id or row["device_id"], chat_device_id or row["chat_device_id"],
         max_slots, now, now, now, row["id"])
    )
    conn.commit()
    return (row["id"], 2, "签入成功")


# ═══════════════════════════════════════════════════════════════
#  3. 坐席就绪 (AgentReady)
# ═══════════════════════════════════════════════════════════════

def robot_agent_ready(
    conn: sqlite3.Connection, ccc_agent_id: str, outbound_scenario: int = 0,
) -> tuple:
    cur = conn.execute("SELECT * FROM robot_agent WHERE ccc_agent_id = ?", (ccc_agent_id,))
    row = cur.fetchone()
    if not row:
        return (0, 0, "坐席不存在")
    now = _now()
    conn.execute(
        "UPDATE robot_agent SET agent_status=2, outbound_scenario=?, "
        "last_event='AgentReady', last_event_time=?, updated_time=? WHERE id=?",
        (outbound_scenario, now, now, row["id"])
    )
    conn.commit()
    return (row["id"], 2, "坐席已就绪")


# ═══════════════════════════════════════════════════════════════
#  4. 坐席小休 (AgentBreak)
# ═══════════════════════════════════════════════════════════════

def robot_agent_break(
    conn: sqlite3.Connection, ccc_agent_id: str, break_code: str = "Warm-up",
) -> tuple:
    cur = conn.execute("SELECT * FROM robot_agent WHERE ccc_agent_id = ?", (ccc_agent_id,))
    row = cur.fetchone()
    if not row:
        return (0, 0, "坐席不存在")
    now = _now()
    conn.execute(
        "UPDATE robot_agent SET agent_status=1, break_code=?, "
        "last_event='AgentBreak', last_event_time=?, updated_time=? WHERE id=?",
        (break_code, now, now, row["id"])
    )
    conn.commit()
    return (row["id"], 1, f"坐席已小休: {break_code}")


# ═══════════════════════════════════════════════════════════════
#  5. 坐席签出 (AgentCheckOut)
# ═══════════════════════════════════════════════════════════════

def robot_agent_check_out(conn: sqlite3.Connection, ccc_agent_id: str) -> tuple:
    cur = conn.execute("SELECT * FROM robot_agent WHERE ccc_agent_id = ?", (ccc_agent_id,))
    row = cur.fetchone()
    if not row:
        return (0, 0, "坐席不存在")
    now = _now()
    conn.execute(
        "UPDATE robot_agent SET agent_status=0, contact_id=NULL, channel_id=NULL, "
        "call_type=NULL, ringing_slots=0, talking_slots=0, break_code=NULL, "
        "last_event='AgentCheckOut', last_event_time=?, check_in_time=NULL, updated_time=? "
        "WHERE id=?", (now, now, row["id"])
    )
    conn.commit()
    return (row["id"], 0, "坐席已签出")


# ═══════════════════════════════════════════════════════════════
#  6. 坐席开始通话 (AgentTalk)
# ═══════════════════════════════════════════════════════════════

def robot_agent_talk(
    conn: sqlite3.Connection, ccc_agent_id: str, contact_id: str,
    channel_id: Optional[str] = None, call_type: str = "INBOUND",
    skill_group_id: Optional[str] = None, ringing_slots: int = 0,
    talking_slots: int = 1,
) -> tuple:
    cur = conn.execute("SELECT * FROM robot_agent WHERE ccc_agent_id = ?", (ccc_agent_id,))
    row = cur.fetchone()
    if not row:
        try:
            slot_id = int(ccc_agent_id)
            cur = conn.execute("SELECT * FROM robot_agent WHERE slot_id = ?", (slot_id,))
            row = cur.fetchone()
        except ValueError:
            return (0, 0, "坐席不存在")
    if not row:
        return (0, 0, "坐席不存在")
    now = _now()
    conn.execute(
        "UPDATE robot_agent SET agent_status=1, contact_id=?, channel_id=?, "
        "call_type=?, skill_group_id=?, ringing_slots=?, talking_slots=?, "
        "last_event='AgentTalk', last_event_time=?, updated_time=? WHERE id=?",
        (contact_id, channel_id or row["channel_id"], call_type,
         skill_group_id or row["skill_group_id"], ringing_slots, talking_slots,
         now, now, row["id"])
    )
    conn.commit()
    return (row["id"], 1, f"坐席通话中: {contact_id}")


# ═══════════════════════════════════════════════════════════════
#  7. 坐席释放通话 (AgentRelease)
# ═══════════════════════════════════════════════════════════════

def robot_agent_release(
    conn: sqlite3.Connection, ccc_agent_id: str, transferee: Optional[str] = None,
) -> tuple:
    cur = conn.execute("SELECT * FROM robot_agent WHERE ccc_agent_id = ?", (ccc_agent_id,))
    row = cur.fetchone()
    if not row:
        try:
            slot_id = int(ccc_agent_id)
            cur = conn.execute("SELECT * FROM robot_agent WHERE slot_id = ?", (slot_id,))
            row = cur.fetchone()
        except ValueError:
            return (0, 0, "坐席不存在")
    if not row:
        return (0, 0, "坐席不存在")
    now = _now()
    msg = "坐席已释放通话"
    if transferee:
        msg += f" (转接至 {transferee})"
    conn.execute(
        "UPDATE robot_agent SET agent_status=2, contact_id=NULL, channel_id=NULL, "
        "call_type=NULL, ringing_slots=0, talking_slots=0, "
        "last_event='AgentRelease', last_event_time=?, updated_time=? WHERE id=?",
        (now, now, row["id"])
    )
    conn.commit()
    return (row["id"], 2, msg)


# ═══════════════════════════════════════════════════════════════
#  8. 坐席振铃 (AgentRinging)
# ═══════════════════════════════════════════════════════════════

def robot_agent_ringing(
    conn: sqlite3.Connection, ccc_agent_id: str, contact_id: str,
    channel_id: Optional[str] = None, call_type: str = "INBOUND",
    skill_group_id: Optional[str] = None, ringing_slots: int = 1,
    talking_slots: int = 0,
) -> tuple:
    cur = conn.execute("SELECT * FROM robot_agent WHERE ccc_agent_id = ?", (ccc_agent_id,))
    row = cur.fetchone()
    if not row:
        return (0, 0, "坐席不存在")
    now = _now()
    conn.execute(
        "UPDATE robot_agent SET agent_status=1, contact_id=?, channel_id=?, "
        "call_type=?, skill_group_id=?, ringing_slots=?, talking_slots=?, "
        "last_event='AgentRinging', last_event_time=?, updated_time=? WHERE id=?",
        (contact_id, channel_id or row["channel_id"], call_type,
         skill_group_id or row["skill_group_id"], ringing_slots, talking_slots,
         now, now, row["id"])
    )
    conn.commit()
    return (row["id"], 1, f"坐席振铃中: {contact_id}")


# ═══════════════════════════════════════════════════════════════
#  9. 按 slot_id 更新状态（核心函数，供 Redis 同步使用）
# ═══════════════════════════════════════════════════════════════

def robot_agent_update_by_slot(
    conn: sqlite3.Connection, slot_id: int, status: int,
    contact_id: Optional[str] = None,
) -> tuple:
    """
    按槽位编号更新坐席状态
    status: 0=离线, 1=忙碌, 2=在线空闲
    """
    cur = conn.execute("SELECT * FROM robot_agent WHERE slot_id = ?", (slot_id,))
    row = cur.fetchone()
    if not row:
        return (0, 0, f"槽位 {slot_id} 不存在")

    event_map = {0: "AgentCheckOut", 1: "AgentTalk", 2: "AgentReady"}
    event = event_map.get(status, "AgentStatusChange")
    status_text = {0: "离线", 1: "忙碌", 2: "在线空闲"}
    now = _now()

    if status == 1:
        conn.execute(
            "UPDATE robot_agent SET agent_status=1, contact_id=?, "
            "ringing_slots=1, talking_slots=1, "
            "last_event=?, last_event_time=?, updated_time=? WHERE id=?",
            (contact_id or row["contact_id"], event, now, now, row["id"])
        )
    else:
        conn.execute(
            "UPDATE robot_agent SET agent_status=?, contact_id=NULL, "
            "ringing_slots=0, talking_slots=0, "
            "last_event=?, last_event_time=?, updated_time=? WHERE id=?",
            (status, event, now, now, row["id"])
        )
    conn.commit()
    return (row["id"], status, f"槽位 {slot_id} → {status_text.get(status, '未知')}")


# ═══════════════════════════════════════════════════════════════
#  10. 查询视图（替代 PostgreSQL VIEW）
# ═══════════════════════════════════════════════════════════════

def query_robot_agent_status(conn: sqlite3.Connection) -> list:
    """替代 v_robot_agent_status 视图"""
    cur = conn.execute(
        "SELECT id, agent_name, slot_id, agent_status, ccc_agent_id, "
        "skill_group_id, skill_level, work_mode, max_slots, "
        "ringing_slots, talking_slots, call_type, contact_id, break_code, "
        "last_event, last_event_time, check_in_time "
        "FROM robot_agent ORDER BY slot_id"
    )
    return [dict(row) for row in cur.fetchall()]


def query_robot_agent_summary(conn: sqlite3.Connection) -> dict:
    """替代 v_robot_agent_summary 视图"""
    cur = conn.execute(
        "SELECT "
        "COUNT(*) AS total, "
        "SUM(CASE WHEN agent_status=2 THEN 1 ELSE 0 END) AS online_idle, "
        "SUM(CASE WHEN agent_status=1 THEN 1 ELSE 0 END) AS busy, "
        "SUM(CASE WHEN agent_status=0 THEN 1 ELSE 0 END) AS offline, "
        "SUM(CASE WHEN agent_status=1 AND break_code IS NOT NULL THEN 1 ELSE 0 END) AS on_break, "
        "SUM(CASE WHEN agent_status=1 AND contact_id IS NOT NULL THEN 1 ELSE 0 END) AS in_call, "
        "COALESCE(SUM(ringing_slots + talking_slots), 0) AS total_active_sessions, "
        "COALESCE(SUM(max_slots), 0) AS total_max_slots "
        "FROM robot_agent"
    )
    row = cur.fetchone()
    result = dict(row)
    total_max = result["total_max_slots"] or 1
    result["load_pct"] = round(result["total_active_sessions"] / total_max * 100, 1)
    return result
