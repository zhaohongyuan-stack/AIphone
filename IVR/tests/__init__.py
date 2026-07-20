"""
测试包：导出辅助函数供 DB 同事脚本使用

DB 同事可通过以下方式调用:
    from tests.helpers import create_test_order, simulate_ivr_event, ...
    # 或
    from tests import create_test_order, simulate_ivr_event, ...

使用时需要先启动 FastAPI 服务:
    python main.py
然后用 httpx 指向服务地址:
    import httpx
    client = httpx.Client(base_url="http://localhost:8000")
    result = create_test_order(client, "13800138001", "conv-001")
"""
from tests.helpers import (
    create_test_order,
    simulate_ivr_event,
    simulate_call_started,
    simulate_ivr_key,
    simulate_hangup,
    assign_robot_slot,
    release_robot_slot,
    simulate_dialogue,
    get_order,
    get_orders_by_phone,
    get_slot_status,
    get_agents,
    update_agent_status,
    dispatch_order,
)
