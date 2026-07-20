"""
自动初始化 robot_agent.db（SQLite）
- 创建 robot_agent 表 + 索引
- 初始化机器人坐席记录（根据 ROBOT_SLOT_COUNT）

在服务启动时自动调用，无需手动执行 SQL 脚本。
"""
import logging

from config import settings
from database.robot_agent_db import (
    get_connection, create_tables, init_robot_agents
)

logger = logging.getLogger(__name__)


def init_robot_agent_db() -> bool:
    """
    初始化 SQLite robot_agent.db：
    1. 建表 + 索引
    2. 初始化机器人坐席记录（根据 ROBOT_SLOT_COUNT）
    """
    try:
        conn = get_connection()
        create_tables(conn)
        result = init_robot_agents(conn, slot_count=settings.ROBOT_SLOT_COUNT)
        conn.close()
        if result:
            logger.info(f"已初始化 {len(result)} 个机器人坐席记录")
        else:
            logger.info("机器人坐席记录已存在，跳过初始化")
        return True
    except Exception as e:
        logger.error(f"robot_agent.db 初始化失败: {e}")
        return False


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    success = init_robot_agent_db()
    print(f"初始化{'成功' if success else '失败'}")
