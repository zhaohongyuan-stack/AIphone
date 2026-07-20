"""
测试辅助函数
供 pytest 测试脚本和 DB 同事脚本共用
兼容 TestClient（base_url=""）和 httpx/requests（base_url="http://localhost:8000"）
"""
import json
from typing import Optional


def create_test_order(client, phone: str, conv_id: str, order_type: int = 1,
                      instance_id: str = "ccc-test-instance",
                      base_url: str = "") -> dict:
    """创建测试工单，返回 {code, data: {order_id}}"""
    resp = client.post(f"{base_url}/api/orders", json={
        "phone": phone,
        "conversation_id": conv_id,
        "instance_id": instance_id,
        "order_type": order_type,
    })
    return resp.json()


def simulate_ivr_event(client, event_type: str, conversation_id: str,
                       key: Optional[str] = None, caller: Optional[str] = None,
                       instance_id: Optional[str] = None,
                       base_url: str = "") -> dict:
    """模拟发送 CCC 事件到 /api/ccc/callback"""
    payload = {"EventType": event_type, "ConversationId": conversation_id}
    if key is not None:
        payload["Key"] = key
    if caller:
        payload["Caller"] = caller
    if instance_id:
        payload["InstanceId"] = instance_id
    resp = client.post(f"{base_url}/api/ccc/callback", json=payload)
    return resp.json()


def simulate_call_started(client, conversation_id: str, phone: str,
                          instance_id: str = "ccc-test-instance",
                          base_url: str = "") -> dict:
    """模拟来电接入（CallStarted 事件）"""
    return simulate_ivr_event(
        client, "CallStarted", conversation_id,
        caller=phone, instance_id=instance_id, base_url=base_url,
    )


def simulate_ivr_key(client, conversation_id: str, key: str,
                     base_url: str = "") -> dict:
    """模拟 IVR 按键事件"""
    return simulate_ivr_event(
        client, "IvrKeyPressed", conversation_id,
        key=key, base_url=base_url,
    )


def simulate_dtmf(client, conversation_id: str, dtmf: str,
                  base_url: str = "") -> dict:
    """模拟 DTMF 按键事件（对话中按键转人工）"""
    payload = {
        "EventType": "DtmfResult",
        "ConversationId": conversation_id,
        "Dtmf": dtmf,
    }
    resp = client.post(f"{base_url}/api/ccc/callback", json=payload)
    return resp.json()


def simulate_hangup(client, conversation_id: str, hangup_dir: str = "User",
                    base_url: str = "") -> dict:
    """模拟挂断事件"""
    payload = {
        "EventType": "CallHangup",
        "ConversationId": conversation_id,
        "HangupDir": hangup_dir,
    }
    resp = client.post(f"{base_url}/api/ccc/callback", json=payload)
    return resp.json()


def assign_robot_slot(client, order_id: int, phone: str,
                      base_url: str = "") -> dict:
    """分配智能坐席槽位"""
    resp = client.post(
        f"{base_url}/api/robot-slots/assign",
        params={"order_id": order_id, "phone": phone},
    )
    return resp.json()


def release_robot_slot(client, slot_id: int, base_url: str = "") -> dict:
    """释放智能坐席槽位"""
    resp = client.post(f"{base_url}/api/robot-slots/{slot_id}/release")
    return resp.json()


def simulate_dialogue(client, order_id: int, utterance: str,
                      base_url: str = "") -> dict:
    """模拟一轮机器人对话"""
    resp = client.post(f"{base_url}/api/robot/dialogue", json={
        "order_id": order_id,
        "utterance": utterance,
    })
    return resp.json()


def get_order(client, order_id: int, base_url: str = "") -> dict:
    """获取工单详情"""
    resp = client.get(f"{base_url}/api/orders/{order_id}")
    return resp.json()


def get_orders_by_phone(client, phone: str, base_url: str = "") -> dict:
    """根据电话查历史工单"""
    resp = client.get(f"{base_url}/api/orders/by-phone/{phone}")
    return resp.json()


def get_slot_status(client, base_url: str = "") -> dict:
    """获取所有槽位状态"""
    resp = client.get(f"{base_url}/api/robot-slots/status")
    return resp.json()


def get_agents(client, base_url: str = "") -> dict:
    """获取所有坐席列表"""
    resp = client.get(f"{base_url}/api/agents")
    return resp.json()


def update_agent_status(client, agent_id: int, agent_status: int,
                        ccc_agent_id: str = None,
                        device_id: str = None, base_url: str = "") -> dict:
    """更新坐席状态"""
    payload = {"agent_id": agent_id, "agent_status": agent_status}
    if ccc_agent_id:
        payload["ccc_agent_id"] = ccc_agent_id
    if device_id:
        payload["device_id"] = device_id
    resp = client.put(f"{base_url}/api/agent/status", json=payload)
    return resp.json()


def dispatch_order(client, order_id: int, receiver: str = "backend_processor",
                   base_url: str = "") -> dict:
    """工单完结流转推送"""
    resp = client.post(
        f"{base_url}/api/orders/{order_id}/dispatch",
        json={"receiver": receiver},
    )
    return resp.json()


# ═══════════════════════════════════════════════════════════════
#  人工坐席辅助函数
# ═══════════════════════════════════════════════════════════════

def get_agent_queue(client, base_url: str = "") -> dict:
    """查看人工坐席排队队列"""
    resp = client.get(f"{base_url}/api/agent/queue")
    return resp.json()


def get_agent_queue_status(client, base_url: str = "") -> dict:
    """查看人工坐席队列详细状态"""
    resp = client.get(f"{base_url}/api/agent/queue/status")
    return resp.json()


def agent_accept_order(client, agent_id: int, order_id: int = None,
                       base_url: str = "") -> dict:
    """人工坐席接单"""
    payload = {"agent_id": agent_id}
    if order_id:
        payload["order_id"] = order_id
    resp = client.post(f"{base_url}/api/agent/accept", json=payload)
    return resp.json()


def agent_complete_order(client, order_id: int, agent_id: int = None,
                         manual_summary: str = None,
                         base_url: str = "") -> dict:
    """人工坐席办结工单"""
    payload = {"order_id": order_id}
    if agent_id:
        payload["agent_id"] = agent_id
    if manual_summary:
        payload["manual_summary"] = manual_summary
    resp = client.post(f"{base_url}/api/agent/complete", json=payload)
    return resp.json()


def simulate_human_dialogue(client, order_id: int, message: str,
                            role: str = "user", agent_id: int = None,
                            base_url: str = "") -> dict:
    """
    模拟人工坐席对话
    role="user"  → 用户发言
    role="worker" → 坐席发言
    """
    payload = {"order_id": order_id, "message": message, "role": role}
    if agent_id:
        payload["agent_id"] = agent_id
    resp = client.post(f"{base_url}/api/agent/dialogue", json=payload)
    return resp.json()
