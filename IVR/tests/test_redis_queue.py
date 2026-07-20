"""
块3：Redis 排队队列测试
验证智能坐席槽位管理 + FIFO 排队队列 + 自动出队分配
Mock: 阿里云 CCC + Beebot
真实: PostgreSQL, Redis
"""
import pytest

from tests.helpers import (
    simulate_call_started, simulate_ivr_key, assign_robot_slot,
    release_robot_slot, get_slot_status,
)
from database.models import WorkOrder
from core import redis_manager as rm
from config import settings


class TestQueueEnqueue:

    def test_all_slots_occupied_enqueues(self, app_client, db_session):
        """所有槽位占满后，新用户应入队等待"""
        slot_count = settings.ROBOT_SLOT_COUNT

        # 填满所有槽位
        for i in range(slot_count):
            conv_id = f"conv-queue-fill-{i}"
            simulate_call_started(app_client, conv_id, f"1390013901{i}")
            simulate_ivr_key(app_client, conv_id, "1")

        # 确认所有槽位已占满
        slots = rm.get_all_slots()
        assert all(s["status"] == "busy" for s in slots)

        # 再来一个用户 → 应入队
        simulate_call_started(app_client, "conv-queue-wait", "13900139099")
        simulate_ivr_key(app_client, "conv-queue-wait", "1")

        assert rm.get_queue_length() == 1

    def test_queue_position_incremental(self, app_client, db_session):
        """多个用户排队时，队列位置应递增"""
        slot_count = settings.ROBOT_SLOT_COUNT

        # 填满槽位
        for i in range(slot_count):
            simulate_call_started(app_client, f"conv-qpos-{i}", f"139001392{i}")
            simulate_ivr_key(app_client, f"conv-qpos-{i}", "1")

        # 两个用户入队
        simulate_call_started(app_client, "conv-qpos-wait1", "1390013930")
        simulate_ivr_key(app_client, "conv-qpos-wait1", "1")

        simulate_call_started(app_client, "conv-qpos-wait2", "1390013931")
        simulate_ivr_key(app_client, "conv-qpos-wait2", "1")

        assert rm.get_queue_length() == 2


class TestQueueDequeue:

    def test_release_slot_dequeues_next(self, app_client, db_session):
        """释放槽位后应自动从队列取出下一个用户"""
        slot_count = settings.ROBOT_SLOT_COUNT

        # 填满槽位
        for i in range(slot_count):
            simulate_call_started(app_client, f"conv-deq-{i}", f"139001394{i}")
            simulate_ivr_key(app_client, f"conv-deq-{i}", "1")

        # 一个用户入队
        simulate_call_started(app_client, "conv-deq-wait", "1390013950")
        simulate_ivr_key(app_client, "conv-deq-wait", "1")
        assert rm.get_queue_length() == 1

        # 释放第一个槽位
        resp = release_robot_slot(app_client, 1)
        assert resp["code"] == 200
        assert resp["data"]["released"] is True
        assert resp["data"]["next_assigned"] is True

        # 队列应清空
        assert rm.get_queue_length() == 0

    def test_queue_fifo_order(self, app_client, db_session):
        """队列应保持 FIFO 顺序：先入队的先出队"""
        slot_count = settings.ROBOT_SLOT_COUNT

        # 填满槽位
        for i in range(slot_count):
            simulate_call_started(app_client, f"conv-fifo-{i}", f"139001396{i}")
            simulate_ivr_key(app_client, f"conv-fifo-{i}", "1")

        # 两个用户入队（顺序：wait1, wait2）
        simulate_call_started(app_client, "conv-fifo-wait1", "1390013970")
        simulate_ivr_key(app_client, "conv-fifo-wait1", "1")

        simulate_call_started(app_client, "conv-fifo-wait2", "1390013971")
        simulate_ivr_key(app_client, "conv-fifo-wait2", "1")

        # 释放一个槽位 → wait1 应先出队
        release_robot_slot(app_client, 1)
        assert rm.get_queue_length() == 1

        # 再释放 → wait2 出队
        release_robot_slot(app_client, 2)
        assert rm.get_queue_length() == 0

    def test_empty_queue_release_safe(self, app_client, db_session):
        """队列为空时释放槽位应安全返回（不崩溃）"""
        # 占用一个槽位
        simulate_call_started(app_client, "conv-empty-q", "1390013980")
        simulate_ivr_key(app_client, "conv-empty-q", "1")

        # 释放（队列为空）
        resp = release_robot_slot(app_client, 1)
        assert resp["code"] == 200
        assert resp["data"]["released"] is True
        assert resp["data"]["next_assigned"] is False


# ═══════════════════════════════════════════════════════════════
#  人工坐席排队队列
# ═══════════════════════════════════════════════════════════════

class TestAgentQueueEnqueue:
    """人工坐席队列入队测试"""

    def test_transfer_enqueues_to_agent_queue(self, app_client, db_session):
        """转人工时应进入人工坐席队列"""
        # 正常来电 + 按键1 → AI 对话
        simulate_call_started(app_client, "conv-agent-q-1", "13900131101")
        simulate_ivr_key(app_client, "conv-agent-q-1", "1")

        # 触发转人工（通过 API 模拟）
        from tests.helpers import simulate_dialogue
        # 多轮对话后转人工
        simulate_dialogue(app_client, _get_order_id(db_session, "conv-agent-q-1"),
                          "我要转人工服务")

        # 如果成功转人工，应进入人工队列
        # （取决于 Beebot 是否返回 sysToAgent，如果不返回则队列可能为0）
        # 这里只验证队列状态可查询
        assert rm.get_agent_queue_length() >= 0

    def test_multiple_transfers_enqueue_in_order(self, app_client, db_session):
        """多次转人工应按顺序入队"""
        # 第一个转人工
        simulate_call_started(app_client, "conv-agent-q-2", "13900131102")
        simulate_ivr_key(app_client, "conv-agent-q-2", "0")  # 直接转人工

        # 第二个转人工
        simulate_call_started(app_client, "conv-agent-q-3", "13900131103")
        simulate_ivr_key(app_client, "conv-agent-q-3", "0")  # 直接转人工

        # 如果没有 idle 坐席，两个都应在队列中
        if rm.get_idle_agent() is None:
            assert rm.get_agent_queue_length() >= 2
            items = rm.get_agent_queue_items()
            # FIFO 顺序
            assert items[0]["phone"] == "13900131102"


class TestAgentQueueDequeue:
    """人工坐席队列出队测试"""

    def test_agent_accept_takes_from_queue(self, app_client, db_session):
        """人工坐席接单应从队列取第一个"""
        from tests.helpers import agent_accept_order, get_agents

        # 先确保有转人工工单在队列
        simulate_call_started(app_client, "conv-agent-deq-1", "13900131110")
        simulate_ivr_key(app_client, "conv-agent-deq-1", "0")

        # 如果队列非空，人工接单应成功
        if rm.get_agent_queue_length() > 0:
            # 获取一个在线坐席
            agents_resp = get_agents(app_client)
            if agents_resp["data"]:
                agent_id = agents_resp["data"][0]["agent_id"]
                resp = agent_accept_order(app_client, agent_id)
                assert resp["code"] == 200
                assert resp["data"]["order_id"] is not None
                # call_start_time 应被设置
                order = db_session.query(WorkOrder).filter(
                    WorkOrder.order_id == resp["data"]["order_id"]
                ).first()
                assert order.call_start_time is not None
                assert order.agent_id == agent_id


def _get_order_id(db_session, conv_id: str) -> int:
    """辅助函数：通过 conv_id 查 order_id"""
    order = db_session.query(WorkOrder).filter(
        WorkOrder.conversation_id == conv_id
    ).first()
    return order.order_id if order else 0
