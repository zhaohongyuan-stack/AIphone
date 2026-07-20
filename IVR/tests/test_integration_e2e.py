"""
块4：端到端集成测试
模拟完整通话生命周期：IVR 分流 → Beebot 对话 → 转人工/挂断 → 工单办结
IVR 和智能对话机器人相互来回交互，使用假数据
真实调用: Beebot API, CCC API, PostgreSQL, Redis, LLM Skill（DashScope 真实调用）
事件通道: 通过 /api/ccc/callback 直接 POST 假 CCC 事件（绕过 RocketMQ）
"""
import json
import os
import pytest

from tests.helpers import (
    simulate_call_started, simulate_ivr_key, simulate_hangup,
    simulate_dialogue, get_order, get_slot_status,
    agent_accept_order, agent_complete_order, simulate_human_dialogue,
    get_agents, update_agent_status,
)
from database.models import WorkOrder, DialogueDetail
from core import redis_manager as rm
from config import settings


def _load_scenarios():
    """加载集成测试场景配置"""
    path = os.path.join(os.path.dirname(__file__), "test_data", "integration_scenarios.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["scenarios"]


def _run_scenario(app_client, db_session, scenario):
    """执行单个集成测试场景（真实 Beebot 决定回复内容）"""
    conv_id = scenario["conversation_id"]
    phone = scenario["phone"]
    ivr_key = scenario["ivr_key"]

    # 如果需要预填满槽位
    if scenario.get("pre_fill_slots"):
        slot_count = settings.ROBOT_SLOT_COUNT
        for i in range(slot_count):
            fill_conv = f"{conv_id}-fill-{i}"
            simulate_call_started(app_client, fill_conv, f"139001399{i}")
            simulate_ivr_key(app_client, fill_conv, "1")

    # Step 1: 来电接入
    simulate_call_started(app_client, conv_id, phone)

    # Step 2: IVR 按键分流
    simulate_ivr_key(app_client, conv_id, ivr_key)

    # 查找工单
    order = db_session.query(WorkOrder).filter(
        WorkOrder.conversation_id == conv_id
    ).first()
    assert order is not None, f"场景 {scenario['id']}: 工单未创建"

    # 验证工单类型
    assert order.order_type == scenario["expect_order_type"], \
        f"场景 {scenario['id']}: 工单类型不匹配"

    # Step 3: 多轮对话（真实 Beebot 决定回复）
    transfer_happened = False
    for utterance in scenario["dialogues"]:
        resp = simulate_dialogue(app_client, order.order_id, utterance)
        assert resp["code"] == 200, f"场景 {scenario['id']}: 对话接口返回错误"
        assert resp["data"]["answer"], f"场景 {scenario['id']}: Beebot 返回空回复"

        # 如果触发了转人工，验证并结束
        if resp["data"].get("action") == "transfer_to_agent":
            assert scenario["expect_transfer"], \
                f"场景 {scenario['id']}: 未预期转人工"
            transfer_happened = True

            db_session.expire_all()
            order = db_session.query(WorkOrder).filter(
                WorkOrder.order_id == order.order_id
            ).first()
            assert order.ai_solved == 0
            break

    # Step 4: 挂断（如果未转人工）
    if not transfer_happened:
        simulate_hangup(app_client, conv_id, scenario["hangup_dir"])

    # 验证最终状态
    db_session.expire_all()
    order = db_session.query(WorkOrder).filter(
        WorkOrder.order_id == order.order_id
    ).first()

    if scenario["expect_ai_solved"] and not transfer_happened:
        assert order.ai_solved == 1, \
            f"场景 {scenario['id']}: 预期 AI 解决但 ai_solved != 1"
        assert order.order_status == 2, \
            f"场景 {scenario['id']}: 预期工单办结但 status != 2"
        # AI 解决: call_start_time 不为 null (NOT NULL), call_end_time 应为 null
        assert order.call_start_time is not None, \
            f"场景 {scenario['id']}: AI解决但 call_start_time 为 null"
        assert order.call_end_time is None, \
            f"场景 {scenario['id']}: AI解决但 call_end_time 不为 null"

    if scenario["expect_transfer"]:
        assert order.ai_solved == 0, \
            f"场景 {scenario['id']}: 预期转人工但 ai_solved != 0"
        assert order.ai_failure_note is not None, \
            f"场景 {scenario['id']}: 转人工失败原因为空"
        # ai_failure_note 非空即可（直接转人工无对话时为转人工原因，有对话时为LLM摘要）
        assert len(order.ai_failure_note) > 0, \
            f"场景 {scenario['id']}: ai_failure_note 为空字符串"

    # 验证对话记录
    dialogues = db_session.query(DialogueDetail).filter(
        DialogueDetail.order_id == order.order_id
    ).all()
    expected_dialogue_count = len(scenario["dialogues"]) * 2 + 1  # user+AI 每轮 + 开场白
    assert len(dialogues) >= expected_dialogue_count - 1, \
        f"场景 {scenario['id']}: 对话记录数量不足 ({len(dialogues)} < {expected_dialogue_count - 1})"


# ═══════════════════════════════════════════════════════════════
#  端到端场景测试
# ═══════════════════════════════════════════════════════════════

class TestE2EScenarios:

    def test_consultation_ai_resolved(self, app_client, db_session):
        """场景1：企业咨询 → 3轮对话 → 用户挂断 → AI解决"""
        scenarios = _load_scenarios()
        scenario = next(s for s in scenarios if s["id"] == "consultation_ai_resolved")
        _run_scenario(app_client, db_session, scenario)

    def test_consultation_transfer_to_human(self, app_client, db_session):
        """场景2：企业咨询 → 2轮对话 → 用户要求转人工"""
        scenarios = _load_scenarios()
        scenario = next(s for s in scenarios if s["id"] == "consultation_transfer_to_human")
        _run_scenario(app_client, db_session, scenario)

    def test_complaint_ai_resolved(self, app_client, db_session):
        """场景3：投诉 → 3轮对话 → 用户挂断 → AI解决"""
        scenarios = _load_scenarios()
        scenario = next(s for s in scenarios if s["id"] == "complaint_ai_resolved")
        _run_scenario(app_client, db_session, scenario)

    def test_direct_transfer(self, app_client, db_session):
        """场景4：按键0 → 直接转人工（无对话）"""
        scenarios = _load_scenarios()
        scenario = next(s for s in scenarios if s["id"] == "direct_transfer")
        _run_scenario(app_client, db_session, scenario)

    def test_queue_waiting(self, app_client, db_session):
        """场景5：槽位满 → 排队 → 释放一个槽位 → 自动分配 → 对话 → 挂断"""
        scenarios = _load_scenarios()
        scenario = next(s for s in scenarios if s["id"] == "queue_waiting")
        conv_id = scenario["conversation_id"]
        phone = scenario["phone"]

        # Step 1: 预填满所有槽位
        slot_count = settings.ROBOT_SLOT_COUNT
        fill_conv_ids = []
        for i in range(slot_count):
            fill_conv = f"{conv_id}-fill-{i}"
            fill_conv_ids.append(fill_conv)
            simulate_call_started(app_client, fill_conv, f"139001399{i}")
            simulate_ivr_key(app_client, fill_conv, "1")

        # Step 2: 新来电 → IVR 按键 → 进入排队（槽位已满）
        simulate_call_started(app_client, conv_id, phone)
        simulate_ivr_key(app_client, conv_id, scenario["ivr_key"])

        order = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == conv_id
        ).first()
        assert order is not None, "工单未创建"
        assert order.order_type == scenario["expect_order_type"]

        # 验证已进入排队队列
        assert rm.get_queue_length() >= 1, "未进入排队队列"

        # Step 3: 释放一个槽位（模拟第一个预填通话挂断）→ 触发自动分配
        first_fill_conv = fill_conv_ids[0]
        simulate_hangup(app_client, first_fill_conv, "User")

        # Step 4: 排队用户应被自动分配槽位
        db_session.expire_all()
        slot_id = rm.find_slot_by_order(order.order_id)
        assert slot_id is not None, "排队用户未被自动分配槽位"

        # Step 5: 多轮对话（已分配槽位，可正常对话）
        transfer_happened = False
        for utterance in scenario["dialogues"]:
            resp = simulate_dialogue(app_client, order.order_id, utterance)
            assert resp["code"] == 200, f"对话接口返回错误: {resp}"
            assert resp["data"]["answer"], "Beebot 返回空回复"

            if resp["data"].get("action") == "transfer_to_agent":
                transfer_happened = True
                break

        # Step 6: 挂断
        if not transfer_happened:
            simulate_hangup(app_client, conv_id, scenario["hangup_dir"])

        # Step 7: 验证最终状态
        db_session.expire_all()
        order = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order.order_id
        ).first()

        # 排队用户被分配后正常对话 → AI 解决（除非转人工）
        if not transfer_happened:
            assert order.ai_solved == 1, \
                f"预期 AI 解决但 ai_solved={order.ai_solved}"
            assert order.order_status == 2, "预期工单办结"


@pytest.mark.skipif(
    not settings.DASHSCOPE_API_KEY,
    reason="DashScope API Key 未配置"
)
class TestDualCallScenarios:
    """双电话场景：一个AI解决，一个转人工解决"""

    def test_dual_call_one_ai_one_human(self, app_client, db_session):
        """
        两个电话同时打进来，各有一个智能坐席接待：
        - 电话A（13900139006）：AI 解决，不转人工
        - 电话B（13900139007）：AI 无法解决 → 转人工 → 人工对话 → 办结
        """
        # ── 准备：所有人工坐席先离线，避免电话B提前被接走 ──
        agents_resp = get_agents(app_client)
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        # ════════════════════════════════════════════════════════════
        # 电话A：AI 解决（不转人工）
        # ════════════════════════════════════════════════════════════
        simulate_call_started(app_client, "conv-dual-A", "13900139006")
        simulate_ivr_key(app_client, "conv-dual-A", "1")

        order_a = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-dual-A"
        ).first()
        assert order_a is not None, "电话A工单未创建"

        # AI 多轮对话（真实 Beebot）
        for utt in ["营业执照怎么办理", "需要什么材料", "好的谢谢"]:
            resp_a = simulate_dialogue(app_client, order_a.order_id, utt)
            assert resp_a["code"] == 200, "电话A对话失败"
            assert resp_a["data"]["answer"], "电话A Beebot空回复"
            # 如果 Beebot 意外触发转人工，跳过后续对话
            if resp_a["data"].get("action") == "transfer_to_agent":
                break

        transfer_a = (
            resp_a["data"].get("action") == "transfer_to_agent"
        )

        # 电话A 挂断（AI 解决场景）
        if not transfer_a:
            simulate_hangup(app_client, "conv-dual-A", "User")

        # ════════════════════════════════════════════════════════════
        # 电话B：AI → 转人工 → 人工对话 → 办结
        # ════════════════════════════════════════════════════════════
        simulate_call_started(app_client, "conv-dual-B", "13900139007")
        simulate_ivr_key(app_client, "conv-dual-B", "1")

        order_b = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-dual-B"
        ).first()
        assert order_b is not None, "电话B工单未创建"

        # AI 对话 → 触发转人工
        transfer_b_happened = False
        for utt in ["我要投诉餐饮卫生问题", "转人工服务"]:
            resp_b = simulate_dialogue(app_client, order_b.order_id, utt)
            assert resp_b["code"] == 200, "电话B对话失败"
            assert resp_b["data"]["answer"], "电话B Beebot空回复"
            if resp_b["data"].get("action") == "transfer_to_agent":
                transfer_b_happened = True
                break

        # 如果 Beebot 没触发转人工，用按键0兜底直接转人工
        if not transfer_b_happened:
            # 直接调用转人工逻辑（通过新的来电+按键0）
            # 这里用直接触发：再发一个按键0事件
            # 但同一个 conv_id 不能再按键，所以用 reject 触发
            # 简化：直接通过 simulate_dialogue 多说几次"转人工"
            for utt in ["我要找人工客服", "请帮我转人工", "人工"]:
                resp_b = simulate_dialogue(app_client, order_b.order_id, utt)
                if resp_b["data"].get("action") == "transfer_to_agent":
                    transfer_b_happened = True
                    break

        # 验证电话B已进入人工队列
        assert transfer_b_happened or rm.get_agent_queue_length() > 0, \
            "电话B未触发转人工"

        db_session.expire_all()
        order_b = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_b.order_id
        ).first()
        assert order_b.ai_solved == 0, "电话B应为AI未解决"
        assert order_b.ai_failure_note is not None, "电话B应有AI摘要"

        # ── 人工坐席上线 + 接单 ──
        agent_id = agents_resp["data"][0]["agent_id"]
        update_agent_status(app_client, agent_id, 1)

        accept_resp = agent_accept_order(app_client, agent_id)
        assert accept_resp["code"] == 200, "人工接单失败"
        accepted_order_id = accept_resp["data"]["order_id"]

        # 如果队列里取到的是电话B的工单
        if accepted_order_id == order_b.order_id:
            # ── 人工坐席与用户多轮对话 ──
            human_dialogues = [
                ("worker", "您好，请问您投诉的是哪家企业？"),
                ("user", "是大东餐厅，在大东路123号"),
                ("worker", "好的，请问具体是什么卫生问题？"),
                ("user", "厨房有老鼠，很不卫生"),
                ("worker", "已记录，我们会尽快派人核实处理，请保持电话畅通"),
            ]
            for role, msg in human_dialogues:
                d_resp = simulate_human_dialogue(
                    app_client, order_b.order_id, msg, role=role,
                    agent_id=agent_id,
                )
                assert d_resp["code"] == 200, f"人工对话保存失败: {d_resp}"

            # ── 人工坐席办结 ──
            complete_resp = agent_complete_order(
                app_client, order_b.order_id, agent_id,
            )
            assert complete_resp["code"] == 200, "人工办结失败"

        # ════════════════════════════════════════════════════════════
        # 验证两个工单的最终状态
        # ════════════════════════════════════════════════════════════
        db_session.expire_all()
        order_a = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_a.order_id
        ).first()
        order_b = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_b.order_id
        ).first()

        # ── 电话A：AI 解决 ──
        if not transfer_a:
            assert order_a.ai_solved == 1, \
                f"电话A应AI解决，但 ai_solved={order_a.ai_solved}"
            assert order_a.order_status == 2, "电话A应已办结"
            assert order_a.call_start_time is not None, \
                "电话A AI解决，call_start_time 应为 not null"
            assert order_a.call_end_time is None, \
                "电话A AI解决，call_end_time 应为 null"
            assert order_a.biz_summary is None, \
                "电话A AI解决，biz_summary 应为 null"
            assert order_a.ai_failure_note is not None, \
                "电话A应有AI对话摘要"

        # ── 电话B：转人工解决 ──
        assert order_b.ai_solved == 0, \
            f"电话B应转人工，但 ai_solved={order_b.ai_solved}"
        assert order_b.order_status == 2, "电话B应已办结"
        assert order_b.call_start_time is not None, \
            "电话B转人工，call_start_time 应有值"
        assert order_b.call_end_time is not None, \
            "电话B转人工，call_end_time 应有值"
        assert order_b.biz_summary is not None, \
            "电话B应有人工处理总结"
        assert order_b.ai_failure_note is not None, \
            "电话B应有AI对话摘要"
        assert order_b.ai_failure_note != order_b.biz_summary, \
            "AI摘要和人工总结应不同"
        assert order_b.agent_id is not None, \
            "电话B应分配了人工坐席"

        # ── 验证对话明细 ──
        dialogues_a = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_a.order_id
        ).all()
        dialogues_b = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_b.order_id
        ).all()

        # 电话A：只有 AI/user 角色（无 worker）
        roles_a = {d.role for d in dialogues_a}
        assert "worker" not in roles_a, "电话A不应有人工坐席对话"

        # 电话B：应有 AI/user + worker/user
        roles_b = {d.role for d in dialogues_b}
        assert "worker" in roles_b, "电话B应有人工坐席对话"
        assert "user" in roles_b, "电话B应有用户对话"
