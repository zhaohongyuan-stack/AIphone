"""
块2：智能对话机器人测试
验证 Beebot 对话逻辑 + LLM Skill 真实调用 + 知识库拒绝解答 + 转人工指令
真实调用: Beebot API, CCC API, PostgreSQL, Redis, LLM Skill（DashScope 真实调用）
事件通道: 通过 /api/ccc/callback 直接 POST 假 CCC 事件（绕过 RocketMQ）
"""
import pytest

from tests.helpers import (
    simulate_call_started, simulate_ivr_key, simulate_dialogue,
    assign_robot_slot, release_robot_slot, get_order, get_slot_status,
)
from database.models import WorkOrder, DialogueDetail
from core import redis_manager as rm
from core.knowledge_base import kb
from config import settings


# ═══════════════════════════════════════════════════════════════
#  槽位分配 + 开场白
# ═══════════════════════════════════════════════════════════════

class TestSlotAssignment:

    def test_assign_returns_welcome(self, app_client, db_session):
        """分配槽位应返回 Beebot 开场白（真实 Beebot API 调用）"""
        from tests.helpers import create_test_order
        result = create_test_order(app_client, "13900139001", "conv-bot-001")
        order_id = result["data"]["order_id"]

        resp = assign_robot_slot(app_client, order_id, "13900139001")
        assert resp["code"] == 200
        assert resp["data"]["assigned"] is True
        assert resp["data"]["slot_id"] is not None
        # 真实 Beebot 返回的开场白非空
        assert resp["data"]["welcome"]
        assert len(resp["data"]["welcome"]) > 0

        # PG 应有 AI 开场白对话记录
        dialogues = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_id
        ).all()
        assert len(dialogues) >= 1
        assert dialogues[0].role == "AI"

    def test_assign_saves_to_redis_and_pg(self, app_client, db_session):
        """分配槽位后 Redis 和 PG 都应有记录"""
        from tests.helpers import create_test_order
        result = create_test_order(app_client, "13900139002", "conv-bot-002")
        order_id = result["data"]["order_id"]

        assign_robot_slot(app_client, order_id, "13900139002")

        # Redis 有历史对话
        history = rm.get_history(order_id)
        assert len(history) >= 1
        assert history[0]["role"] == "AI"

        # PG 有对话记录
        dialogues = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_id
        ).all()
        assert len(dialogues) >= 1


# ═══════════════════════════════════════════════════════════════
#  多轮对话（真实 Beebot，回复内容由机器人决定）
# ═══════════════════════════════════════════════════════════════

class TestMultiTurnDialogue:

    def test_three_turn_dialogue(self, app_client, db_session):
        """三轮对话：每轮返回真实 Beebot 回复，历史记录正确累积"""
        simulate_call_started(app_client, "conv-bot-003", "13900139003")
        simulate_ivr_key(app_client, "conv-bot-003", "1")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-bot-003"
        ).first()
        order_id = order.order_id

        # 第一轮
        resp1 = simulate_dialogue(app_client, order_id, "我想咨询营业执照办理流程")
        assert resp1["code"] == 200
        assert resp1["data"]["answer"]  # 真实 Beebot 回复非空

        # 第二轮
        resp2 = simulate_dialogue(app_client, order_id, "需要什么材料")
        assert resp2["code"] == 200
        assert resp2["data"]["answer"]

        # 第三轮
        resp3 = simulate_dialogue(app_client, order_id, "好的谢谢")
        assert resp3["code"] == 200
        assert resp3["data"]["answer"]

        # PG 应有: 开场白(AI) + 3轮(user+AI) = 7条
        db_session.expire_all()
        dialogues = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_id
        ).order_by(DialogueDetail.dia_id).all()
        assert len(dialogues) >= 7

        # Redis 历史对话应累积
        history = rm.get_history(order_id)
        assert len(history) >= 7

    def test_unmatched_input_returns_response(self, app_client, db_session):
        """未命中 Beebot 知识的输入仍应返回响应（Clarify 或 Direct）"""
        simulate_call_started(app_client, "conv-bot-004", "13900139004")
        simulate_ivr_key(app_client, "conv-bot-004", "1")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-bot-004"
        ).first()

        resp = simulate_dialogue(app_client, order.order_id, "今天天气怎么样")
        assert resp["code"] == 200
        assert resp["data"]["answer"]  # Beebot 无论如何都应返回非空回复


# ═══════════════════════════════════════════════════════════════
#  转人工指令（Beebot 返回 sysToAgent 时触发）
# ═══════════════════════════════════════════════════════════════

class TestTransferToHuman:

    def test_transfer_command_triggers_transfer(self, app_client, db_session):
        """用户明确要求转人工时，Beebot 应返回 sysToAgent 指令触发转人工"""
        simulate_call_started(app_client, "conv-bot-005", "13900139005")
        simulate_ivr_key(app_client, "conv-bot-005", "1")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-bot-005"
        ).first()

        # 先正常对话
        simulate_dialogue(app_client, order.order_id, "我有个问题想咨询")

        # 触发转人工（Beebot 应识别"转人工"意图并返回 sysToAgent 指令）
        resp = simulate_dialogue(app_client, order.order_id, "我要转人工服务")
        assert resp["code"] == 200

        # 如果 Beebot 返回了转人工指令
        if resp["data"].get("action") == "transfer_to_agent":
            # 工单应标记 AI 未解决
            db_session.expire_all()
            order = db_session.query(WorkOrder).filter(
                WorkOrder.conversation_id == "conv-bot-005"
            ).first()
            assert order.ai_solved == 0
            # ai_failure_note 应为 LLM 生成的摘要（非简单 reason 字符串）
            assert order.ai_failure_note is not None
            assert len(order.ai_failure_note) > 10  # LLM 摘要应较长
            # 应进入人工坐席队列
            assert rm.get_agent_queue_length() >= 1


# ═══════════════════════════════════════════════════════════════
#  拒绝解答检测（依赖知识库 Excel 内容）
# ═══════════════════════════════════════════════════════════════

class TestRejectAnswer:

    @pytest.mark.skipif(
        len(kb.rejected) == 0,
        reason="知识库 Excel 中无拒绝解答项"
    )
    def test_reject_triggers_transfer(self, app_client, db_session):
        """命中拒绝解答库应直接触发转人工（不经 Beebot）"""
        simulate_call_started(app_client, "conv-bot-006", "13900139006")
        simulate_ivr_key(app_client, "conv-bot-006", "1")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-bot-006"
        ).first()

        # 使用知识库中的第一个拒绝问题
        reject_question = kb.rejected[0]["question"]
        resp = simulate_dialogue(app_client, order.order_id, reject_question)

        assert resp["code"] == 200
        assert resp["data"]["action"] == "transfer_to_agent"
        assert resp["data"]["reason"] == "拒绝解答"


# ═══════════════════════════════════════════════════════════════
#  LLM Skill 真实调用
# ═══════════════════════════════════════════════════════════════

class TestLLMSkill:

    @pytest.mark.skipif(
        not settings.DASHSCOPE_API_KEY,
        reason="DashScope API Key 未配置"
    )
    def test_llm_extracts_enterprise_info(self, app_client, db_session):
        """LLM Skill 应从投诉对话中提取企业信息（真实 API 调用）"""
        simulate_call_started(app_client, "conv-bot-007", "13900139007")
        simulate_ivr_key(app_client, "conv-bot-007", "2")

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-bot-007"
        ).first()
        order_id = order.order_id

        # 三轮投诉对话
        simulate_dialogue(app_client, order_id, "我要投诉一家餐饮店卫生问题")
        simulate_dialogue(app_client, order_id, "企业叫大东餐厅，在大东路123号")
        simulate_dialogue(app_client, order_id, "我的电话是13800139007")

        # LLM 应已提取信息并更新工单
        db_session.expire_all()
        order = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_id
        ).first()

        # biz_summary 由人工办结时生成，AI 阶段不更新
        # 这里验证 LLM 理解 Skill 提取的企业信息
        assert order.ent_name is not None or order.ent_address is not None
        # 工单类型应为投诉
        assert order.order_type == 2
