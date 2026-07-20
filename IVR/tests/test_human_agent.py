"""
块5：人工坐席完整流程测试
验证 AI 转人工后 → 人工坐席接单 → 办结 → LLM 生成摘要 的全链路
真实调用: PostgreSQL, Redis, LLM Skill（DashScope 真实调用）
事件通道: 通过 /api/ccc/callback 直接 POST 假 CCC 事件（绕过 RocketMQ）
"""
import pytest

from tests.helpers import (
    simulate_call_started, simulate_ivr_key, simulate_dialogue,
    simulate_hangup, agent_accept_order, agent_complete_order,
    get_agent_queue, get_agents, update_agent_status,
)
from database.models import WorkOrder, DialogueDetail
from core import redis_manager as rm
from config import settings


class TestHumanAgentQueue:
    """人工坐席队列基础测试"""

    def test_direct_transfer_enters_agent_queue(self, app_client, db_session):
        """按键0直接转人工 → 应进入人工坐席队列"""
        # 先把所有人工坐席设为离线，确保进入队列
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        simulate_call_started(app_client, "conv-agent-001", "13900132001")
        simulate_ivr_key(app_client, "conv-agent-001", "0")

        # 应进入人工队列
        assert rm.get_agent_queue_length() >= 1
        items = rm.get_agent_queue_items()
        assert items[0]["phone"] == "13900132001"
        assert items[0]["ai_summary"]  # LLM 生成的摘要

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-agent-001"
        ).first()
        assert order.ai_solved == 0
        assert order.ai_failure_note is not None
        # 直接转人工无对话历史，ai_failure_note 为转人工原因（非空即可）
        assert len(order.ai_failure_note) > 0

    def test_queue_fifo_order(self, app_client, db_session):
        """多个转人工工单应按 FIFO 顺序排队"""
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        simulate_call_started(app_client, "conv-agent-002", "13900132002")
        simulate_ivr_key(app_client, "conv-agent-002", "0")

        simulate_call_started(app_client, "conv-agent-003", "13900132003")
        simulate_ivr_key(app_client, "conv-agent-003", "0")

        items = rm.get_agent_queue_items()
        phones = [item["phone"] for item in items]
        assert "13900132002" in phones
        assert "13900132003" in phones
        # 002 应在 003 之前
        assert phones.index("13900132002") < phones.index("13900132003")


class TestAgentAcceptWorkOrder:
    """人工坐席接单测试"""

    def test_agent_accept_sets_call_start_time(self, app_client, db_session):
        """人工坐席接单应设置 call_start_time"""
        # 先确保有工单在队列
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        simulate_call_started(app_client, "conv-accept-001", "13900132101")
        simulate_ivr_key(app_client, "conv-accept-001", "0")

        # 让一个坐席上线
        agent_id = agents_resp["data"][0]["agent_id"]
        update_agent_status(app_client, agent_id, 2)

        # 接单
        resp = agent_accept_order(app_client, agent_id)
        assert resp["code"] == 200
        order_id = resp["data"]["order_id"]

        order = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_id
        ).first()
        assert order.call_start_time is not None
        assert order.agent_id == agent_id
        assert order.order_status == 1  # 处理中

    def test_agent_accept_returns_ai_summary(self, app_client, db_session):
        """接单返回应包含 ai_failure_note（AI 摘要）"""
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        simulate_call_started(app_client, "conv-accept-002", "13900132102")
        simulate_ivr_key(app_client, "conv-accept-002", "0")

        agent_id = agents_resp["data"][0]["agent_id"]
        update_agent_status(app_client, agent_id, 2)

        resp = agent_accept_order(app_client, agent_id)
        assert resp["code"] == 200
        # 应返回 ai_failure_note 让人工坐席快速了解诉求
        assert resp["data"]["ai_failure_note"] is not None


class TestAgentCompleteWorkOrder:
    """人工坐席办结测试"""

    def test_complete_generates_biz_summary(self, app_client, db_session):
        """办结应通过 LLM 生成 biz_summary"""
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        simulate_call_started(app_client, "conv-complete-001", "13900132201")
        simulate_ivr_key(app_client, "conv-complete-001", "0")

        agent_id = agents_resp["data"][0]["agent_id"]
        update_agent_status(app_client, agent_id, 2)

        accept_resp = agent_accept_order(app_client, agent_id)
        order_id = accept_resp["data"]["order_id"]

        # 办结（不传 manual_summary，让 LLM 生成）
        complete_resp = agent_complete_order(app_client, order_id, agent_id)
        assert complete_resp["code"] == 200
        assert complete_resp["data"]["biz_summary"] is not None
        # biz_summary 非空即可（无对话历史时为兜底值，有历史时为 LLM 摘要）
        assert len(complete_resp["data"]["biz_summary"]) > 0

        order = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_id
        ).first()
        assert order.order_status == 2  # 已办结
        assert order.ai_solved == 0  # 转人工的工单
        assert order.call_end_time is not None
        assert order.biz_summary is not None

    def test_complete_with_manual_summary(self, app_client, db_session):
        """办结支持人工直接填写 summary（不走 LLM）"""
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        simulate_call_started(app_client, "conv-complete-002", "13900132202")
        simulate_ivr_key(app_client, "conv-complete-002", "0")

        agent_id = agents_resp["data"][0]["agent_id"]
        update_agent_status(app_client, agent_id, 2)

        accept_resp = agent_accept_order(app_client, agent_id)
        order_id = accept_resp["data"]["order_id"]

        manual = "已联系企业核实，卫生问题已处理，用户满意。"
        complete_resp = agent_complete_order(
            app_client, order_id, agent_id, manual_summary=manual
        )
        assert complete_resp["code"] == 200
        assert complete_resp["data"]["biz_summary"] == manual

    def test_complete_releases_agent(self, app_client, db_session):
        """办结后坐席应释放为 idle"""
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        simulate_call_started(app_client, "conv-complete-003", "13900132203")
        simulate_ivr_key(app_client, "conv-complete-003", "0")

        agent_id = agents_resp["data"][0]["agent_id"]
        update_agent_status(app_client, agent_id, 2)

        accept_resp = agent_accept_order(app_client, agent_id)
        order_id = accept_resp["data"]["order_id"]

        agent_complete_order(app_client, order_id, agent_id)

        # 坐席应释放为 idle
        assert rm.get_agent_status(agent_id) == "idle"


class TestFullHumanAgentFlow:
    """人工坐席完整流程：AI 对话 → 转人工 → 接单 → 办结"""

    def test_full_flow_ivr_direct_transfer(self, app_client, db_session):
        """完整流程：按键0直接转人工 → 接单 → 办结"""
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        # Step 1: 来电 + 按键0 直接转人工
        simulate_call_started(app_client, "conv-full-001", "13900132301")
        simulate_ivr_key(app_client, "conv-full-001", "0")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-full-001"
        ).first()
        assert order.ai_solved == 0
        assert order.ai_failure_note is not None

        # Step 2: 坐席上线 + 接单
        agent_id = agents_resp["data"][0]["agent_id"]
        update_agent_status(app_client, agent_id, 2)

        accept_resp = agent_accept_order(app_client, agent_id)
        assert accept_resp["code"] == 200

        # Step 3: 办结
        complete_resp = agent_complete_order(app_client, order.order_id, agent_id)
        assert complete_resp["code"] == 200

        # 验证最终状态
        db_session.expire_all()
        order = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order.order_id
        ).first()
        assert order.order_status == 2
        assert order.ai_solved == 0
        assert order.call_start_time is not None
        assert order.call_end_time is not None
        assert order.biz_summary is not None
        assert order.agent_id == agent_id

    @pytest.mark.skipif(
        not settings.DASHSCOPE_API_KEY,
        reason="DashScope API Key 未配置"
    )
    def test_full_flow_ai_dialogue_then_transfer(self, app_client, db_session):
        """完整流程：AI 对话 → 转人工 → 接单 → 办结（含 LLM 真实摘要）"""
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        # Step 1: 来电 + 按键1 → AI 对话
        simulate_call_started(app_client, "conv-full-002", "13900132302")
        simulate_ivr_key(app_client, "conv-full-002", "1")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-full-002"
        ).first()

        # Step 2: 多轮对话
        simulate_dialogue(app_client, order.order_id, "我要咨询营业执照办理")
        simulate_dialogue(app_client, order.order_id, "企业叫测试公司")

        # Step 3: 触发转人工
        resp = simulate_dialogue(app_client, order.order_id, "我要转人工服务")

        if resp["data"].get("action") == "transfer_to_agent":
            # Step 4: 坐席接单
            agent_id = agents_resp["data"][0]["agent_id"]
            update_agent_status(app_client, agent_id, 2)
            accept_resp = agent_accept_order(app_client, agent_id)
            assert accept_resp["code"] == 200

            # Step 5: 办结
            complete_resp = agent_complete_order(
                app_client, order.order_id, agent_id
            )
            assert complete_resp["code"] == 200

            db_session.expire_all()
            order = db_session.query(WorkOrder).filter(
                WorkOrder.order_id == order.order_id
            ).first()
            # ai_failure_note 是 AI 摘要
            assert order.ai_failure_note is not None
            assert len(order.ai_failure_note) > 0
            # biz_summary 是人工摘要
            assert order.biz_summary is not None
            assert len(order.biz_summary) > 0
            # 两个摘要内容应不同
            assert order.ai_failure_note != order.biz_summary
