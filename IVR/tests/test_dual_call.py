"""
双电话全链路测试：一个 AI 解决，一个 AI→转人工→人工解决
真实调用: Beebot API, PostgreSQL, Redis, LLM Skill（DashScope 真实调用）
事件通道: 通过 /api/ccc/callback 直接 POST 假 CCC 事件（绕过 RocketMQ）
"""
import pytest

from tests.helpers import (
    simulate_call_started, simulate_ivr_key, simulate_hangup,
    simulate_dialogue, simulate_human_dialogue,
    agent_accept_order, agent_complete_order,
    get_agents, update_agent_status,
)
from database.models import WorkOrder, DialogueDetail
from core import redis_manager as rm
from config import settings


@pytest.mark.skipif(
    not settings.DASHSCOPE_API_KEY,
    reason="DashScope API Key 未配置"
)
class TestDualCall:
    """
    双电话同时打进来，两个智能坐席分别接待。
    电话A: AI 对话机器人解决 → 不转人工
    电话B: AI 对话机器人无法解决 → 转人工 → 人工对话 → 人工办结
    """

    def test_dual_call_one_ai_solved_one_human_solved(
        self, app_client, db_session
    ):
        """
        全链路：两个电话同时打进，两个智能坐席接待
        ┌─────────────────────────────────────────────────┐
        │ 电话A (13900139006)：AI 对话机器人完全解决        │
        │  来电 → 按键1 → AI对话 → 用户满意 → 挂断          │
        │  → ai_solved=1, 不转人工                        │
        ├─────────────────────────────────────────────────┤
        │ 电话B (13900139007)：AI 无法解决 → 转人工解决      │
        │  来电 → 按键1 → AI对话 → 用户要求转人工 → 入队列   │
        │  → 人工坐席接单 → 人工与用户对话 → 人工办结        │
        │  → ai_solved=0, 人工摘要生成                     │
        └─────────────────────────────────────────────────┘
        """
        # ── 准备：所有人工坐席先离线，确保电话B先进队列 ──
        agents_resp = get_agents(app_client)
        agent_id_a = agents_resp["data"][0]["agent_id"]
        agent_id_b = agents_resp["data"][1]["agent_id"]
        for a in agents_resp["data"]:
            update_agent_status(app_client, a["agent_id"], 0)

        # ════════════════════════════════════════════════════════════
        # 电话A：AI 完全解决（不转人工）
        # ════════════════════════════════════════════════════════════
        print("\n========== 电话A：AI 对话机器人解决 ==========")
        simulate_call_started(app_client, "conv-dual-A", "13900139006")
        simulate_ivr_key(app_client, "conv-dual-A", "1")

        order_a = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-dual-A"
        ).first()
        assert order_a is not None, "电话A: 工单未创建"
        print(f"电话A: 工单#{order_a.order_id} 已创建")

        # AI 多轮对话 — 用户咨询营业执照办理
        dialogues_a = [
            "营业执照怎么办理",
            "需要什么材料",
            "好的谢谢",
        ]
        for utt in dialogues_a:
            resp = simulate_dialogue(app_client, order_a.order_id, utt)
            assert resp["code"] == 200
            assert resp["data"]["answer"]
            print(f"电话A: [用户] {utt}")
            print(f"电话A: [AI] {resp['data']['answer'][:80]}...")

        # 挂断（AI 解决）
        simulate_hangup(app_client, "conv-dual-A", "User")
        print("电话A: 已挂断（AI 解决）")

        # ════════════════════════════════════════════════════════════
        # 电话B：AI → 转人工 → 人工对话 → 人工办结
        # ════════════════════════════════════════════════════════════
        print("\n========== 电话B：AI → 转人工 → 人工解决 ==========")
        simulate_call_started(app_client, "conv-dual-B", "13900139007")
        simulate_ivr_key(app_client, "conv-dual-B", "1")

        order_b = db_session.query(WorkOrder).filter(
            WorkOrder.conversation_id == "conv-dual-B"
        ).first()
        assert order_b is not None, "电话B: 工单未创建"
        print(f"电话B: 工单#{order_b.order_id} 已创建")

        # AI 对话 — 用户投诉，触发转人工
        ai_dialogues = [
            "我要投诉一家餐饮店，厨房有老鼠，卫生很差",
            "请帮我转人工服务",
        ]
        transfer_happened = False
        for utt in ai_dialogues:
            resp = simulate_dialogue(app_client, order_b.order_id, utt)
            assert resp["code"] == 200
            assert resp["data"]["answer"]
            print(f"电话B: [用户] {utt}")
            print(f"电话B: [AI] {resp['data']['answer'][:80]}...")
            if resp["data"].get("action") == "transfer_to_agent":
                transfer_happened = True
                print("电话B: 触发转人工!")
                break

        # 如果 Beebot 没自动触发转人工，多试几次
        if not transfer_happened:
            for utt in ["转人工", "我要找人工客服", "人工服务"]:
                resp = simulate_dialogue(app_client, order_b.order_id, utt)
                if resp["data"].get("action") == "transfer_to_agent":
                    transfer_happened = True
                    break

        assert transfer_happened, "电话B: 未触发转人工"
        assert rm.get_agent_queue_length() >= 1, "电话B: 未进入人工队列"

        # 验证转人工后的状态
        db_session.expire_all()
        order_b = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_b.order_id
        ).first()
        assert order_b.ai_solved == 0
        assert order_b.ai_failure_note is not None
        print(f"电话B: AI摘要 = {order_b.ai_failure_note[:80]}...")

        # ── 人工坐席上线 + 接单 ──
        update_agent_status(app_client, agent_id_b, 2)
        accept_resp = agent_accept_order(app_client, agent_id_b)
        assert accept_resp["code"] == 200
        accepted_order_id = accept_resp["data"]["order_id"]
        print(f"电话B: 坐席#{agent_id_b} 接单（工单#{accepted_order_id}）")

        if accepted_order_id == order_b.order_id:
            # ── 人工坐席与用户多轮对话 ──
            human_dialogues = [
                ("worker", "您好，我是市场监督管理局的人工坐席，请问您投诉的是哪家企业？"),
                ("user",   "是大东餐厅，在大东路123号"),
                ("worker", "好的，请问具体是什么卫生问题？"),
                ("user",   "厨房有老鼠，食材乱放，很不卫生"),
                ("worker", "已记录，我们会尽快派人去现场核实，请您保持电话畅通"),
                ("user",   "好的，谢谢"),
                ("worker", "不客气，还有其他问题需要帮助吗？"),
                ("user",   "没有了"),
            ]
            for role, msg in human_dialogues:
                d_resp = simulate_human_dialogue(
                    app_client, order_b.order_id, msg, role=role,
                    agent_id=agent_id_b,
                )
                assert d_resp["code"] == 200, f"电话B: 人工对话保存失败"
                print(f"电话B: [{role}] {msg}")

            # ── 人工坐席办结（LLM 生成 biz_summary）──
            complete_resp = agent_complete_order(
                app_client, order_b.order_id, agent_id_b,
            )
            assert complete_resp["code"] == 200
            print(f"电话B: 已办结，人工摘要 = {complete_resp['data']['biz_summary'][:80]}...")

        # ════════════════════════════════════════════════════════════
        # 最终验证：对比两个工单的存储结果
        # ════════════════════════════════════════════════════════════
        db_session.expire_all()
        order_a = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_a.order_id
        ).first()
        order_b = db_session.query(WorkOrder).filter(
            WorkOrder.order_id == order_b.order_id
        ).first()

        print("\n========== 最终验证 ==========")

        # ── 电话A：AI 解决 ──
        print(f"\n--- 电话A (AI解决) ---")
        print(f"  ai_solved:       {order_a.ai_solved} (期望=1)")
        print(f"  order_status:    {order_a.order_status} (期望=2)")
        print(f"  call_start_time: {order_a.call_start_time} (期望=not null)")
        print(f"  call_end_time:   {order_a.call_end_time} (期望=null)")
        print(f"  biz_summary:     {order_a.biz_summary} (期望=null)")
        print(f"  ai_failure_note: {order_a.ai_failure_note[:50] if order_a.ai_failure_note else None}...")
        assert order_a.ai_solved == 1
        assert order_a.order_status == 2
        assert order_a.call_start_time is not None
        assert order_a.call_end_time is None
        assert order_a.biz_summary is None
        assert order_a.ai_failure_note is not None

        # ── 电话B：转人工解决 ──
        print(f"\n--- 电话B (转人工解决) ---")
        print(f"  ai_solved:       {order_b.ai_solved} (期望=0)")
        print(f"  order_status:    {order_b.order_status} (期望=2)")
        print(f"  call_start_time: {order_b.call_start_time} (期望=有值)")
        print(f"  call_end_time:   {order_b.call_end_time} (期望=有值)")
        print(f"  agent_id:        {order_b.agent_id} (期望=有值)")
        print(f"  ai_failure_note: {order_b.ai_failure_note[:50] if order_b.ai_failure_note else None}...")
        print(f"  biz_summary:     {order_b.biz_summary[:50] if order_b.biz_summary else None}...")
        assert order_b.ai_solved == 0
        assert order_b.order_status == 2
        assert order_b.call_start_time is not None
        assert order_b.call_end_time is not None
        assert order_b.biz_summary is not None
        assert order_b.ai_failure_note is not None
        assert order_b.ai_failure_note != order_b.biz_summary
        assert order_b.agent_id is not None

        # ── 对话记录对比 ──
        dialogues_a = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_a.order_id
        ).order_by(DialogueDetail.dia_id).all()
        dialogues_b = db_session.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_b.order_id
        ).order_by(DialogueDetail.dia_id).all()

        print(f"\n--- 对话记录 ---")
        print(f"电话A: 共 {len(dialogues_a)} 条对话")
        for d in dialogues_a:
            print(f"  [{d.role}] {d.content[:60]}")

        print(f"\n电话B: 共 {len(dialogues_b)} 条对话")
        for d in dialogues_b:
            print(f"  [{d.role}] {d.content[:60]}")

        # 电话A 不应有 worker 对话
        roles_a = {d.role for d in dialogues_a}
        assert "worker" not in roles_a, "电话A 不应有人工坐席对话"

        # 电话B 应有 worker 对话
        roles_b = {d.role for d in dialogues_b}
        assert "worker" in roles_b, "电话B 应有人工坐席对话"
        assert "AI" in roles_b, "电话B 应有AI对话"
        assert "user" in roles_b, "电话B 应有用户对话"

        print("\n✅ 全链路测试通过！")