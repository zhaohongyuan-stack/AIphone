"""
块1：IVR 分流测试
验证 IVR 层分流逻辑 + Redis 来电缓存 + PostgreSQL 工单写入 + 幂等去重
真实调用: PostgreSQL, Redis, CCC API（转人工时调用 BlindTransfer）
事件通道: 通过 /api/ccc/callback 直接 POST 假 CCC 事件（绕过 RocketMQ）
"""
import pytest

from tests.helpers import (
    simulate_call_started, simulate_ivr_key, simulate_hangup,
    simulate_ivr_event, get_order, get_slot_status,
)
from database.models import WorkOrder, DialogueDetail
from core import redis_manager as rm


# ═══════════════════════════════════════════════════════════════
#  CallStarted 事件
# ═══════════════════════════════════════════════════════════════

class TestCallStarted:

    def test_call_started_caches_pending(self, app_client, redis_client):
        """CallStarted 应将来电信息缓存到 Redis"""
        simulate_call_started(app_client, "conv-ivr-001", "13800138001")

        pending = rm.get_pending_call("conv-ivr-001")
        assert pending is not None
        assert pending["phone"] == "13800138001"
        assert pending["instance_id"] == "ccc-test-instance"

    def test_call_started_missing_conv_id(self, app_client):
        """缺少 ConversationId 的 CallStarted 应被安全处理（不崩溃）"""
        resp = app_client.post("/api/ccc/callback", json={
            "EventType": "CallStarted",
            "Caller": "13800000000",
        })
        assert resp.status_code == 200
        assert resp.json()["message"] == "ok"


# ═══════════════════════════════════════════════════════════════
#  IvrKeyPressed 按键分流
# ═══════════════════════════════════════════════════════════════

class TestIvrKeyPressed:

    def test_key_1_creates_consultation(self, app_client, db_session):
        """按键1 → 创建咨询工单(type=1) + 分配智能坐席槽位"""
        simulate_call_started(app_client, "conv-ivr-002", "13800138002")
        simulate_ivr_key(app_client, "conv-ivr-002", "1")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-002"
        ).first()
        assert order is not None
        assert order.order_type == 1
        assert order.order_status == 1
        assert order.phone == "13800138002"

        # Redis 槽位已分配
        slot_id = rm.find_slot_by_order(order.order_id)
        assert slot_id is not None
        slot_info = rm.get_slot_status(slot_id)
        assert slot_info["status"] == "busy"

    def test_key_2_creates_complaint(self, app_client, db_session):
        """按键2 → 创建投诉工单(type=2) + 分配智能坐席槽位"""
        simulate_call_started(app_client, "conv-ivr-003", "13800138003")
        simulate_ivr_key(app_client, "conv-ivr-003", "2")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-003"
        ).first()
        assert order is not None
        assert order.order_type == 2

    def test_key_0_direct_transfer(self, app_client, db_session):
        """按键0 → 创建工单 + 直接转人工（不经 Beebot）"""
        simulate_call_started(app_client, "conv-ivr-004", "13800138004")
        simulate_ivr_key(app_client, "conv-ivr-004", "0")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-004"
        ).first()
        assert order is not None
        assert order.ai_solved == 0
        assert order.ai_failure_note is not None
        # IVR 直接转人工，如果有人工坐席空闲则应分配
        # （取决于是否有 idle 坐席，无 idle 时进入人工队列）

    def test_unknown_key_ignored(self, app_client, db_session):
        """未知按键(9)应被忽略，不创建工单"""
        simulate_call_started(app_client, "conv-ivr-005", "13800138005")
        simulate_ivr_key(app_client, "conv-ivr-005", "9")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-005"
        ).first()
        assert order is None

    def test_duplicate_key_no_duplicate_order(self, app_client, db_session):
        """重复 IvrKeyPressed 不应重复创建工单"""
        simulate_call_started(app_client, "conv-ivr-006", "13800138006")
        simulate_ivr_key(app_client, "conv-ivr-006", "1")
        simulate_ivr_key(app_client, "conv-ivr-006", "1")

        count = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-006"
        ).count()
        assert count == 1


# ═══════════════════════════════════════════════════════════════
#  CallHangup 挂断事件
# ═══════════════════════════════════════════════════════════════

class TestCallHangup:

    def test_hangup_releases_slot_and_completes_order(self, app_client, db_session):
        """CallHangup 应释放槽位 + 工单办结 + AI解决标记"""
        # 建立通话
        simulate_call_started(app_client, "conv-ivr-007", "13800138007")
        simulate_ivr_key(app_client, "conv-ivr-007", "1")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-007"
        ).first()
        slot_id = rm.find_slot_by_order(order.order_id)
        assert slot_id is not None

        # 挂断
        simulate_hangup(app_client, "conv-ivr-007", "User")

        # 验证槽位已释放
        slot_info = rm.get_slot_status(slot_id)
        assert slot_info["status"] == "idle"

        # 验证工单状态
        db_session.expire_all()
        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-007"
        ).first()
        assert order.order_status == 2
        assert order.ai_solved == 1
        # AI 解决: call_start_time 不为 null (NOT NULL), call_end_time 为 null
        assert order.call_start_time is not None
        assert order.call_end_time is None


# ═══════════════════════════════════════════════════════════════
#  事件幂等去重
# ═══════════════════════════════════════════════════════════════

class TestEventDedup:

    def test_same_event_id_deduplicated(self, app_client):
        """相同 EventId 的事件应被幂等去重"""
        payload = {
            "EventType": "CallStarted",
            "ConversationId": "conv-ivr-008",
            "Caller": "13800138008",
            "EventId": "evt-dedup-001",
        }
        resp1 = app_client.post("/api/ccc/callback", json=payload)
        assert resp1.json()["message"] == "ok"

        resp2 = app_client.post("/api/ccc/callback", json=payload)
        assert resp2.json()["message"] == "duplicated"


# ═══════════════════════════════════════════════════════════════
#  ASR 语音转写
# ═══════════════════════════════════════════════════════════════

class TestAsrResult:

    def test_asr_result_saved_to_db(self, app_client, db_session):
        """ASR 转写结果应保存到 dialogue_detail 表"""
        simulate_call_started(app_client, "conv-ivr-009", "13800138009")
        simulate_ivr_key(app_client, "conv-ivr-009", "1")

        app_client.post("/api/ccc/callback", json={
            "EventType": "AsrSentenceResult",
            "ConversationId": "conv-ivr-009",
            "Role": "caller",
            "Text": "我想咨询营业执照办理流程",
        })

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-ivr-009"
        ).first()
        dialogues = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order.order_id
        ).all()
        texts = [d.content for d in dialogues]
        assert any("营业执照" in t for t in texts)
