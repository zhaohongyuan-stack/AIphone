#!/usr/bin/env python3
"""
交互式 IVR 模拟器 — 命令行模拟电话拨入全流程
使用方法:
    python -m tests.ivr_simulator

流程:
    1. 欢迎语 → 按键选择分流（1=企业咨询，2=投诉，0=转人工）
    2. 创建工单 → 进入智能机器人对话
    3. 用户在终端输入文本，调用 AI 对话，AI 返回回答在终端显示
    4. 对话过程中随时可以输入 "0"（单独一行）→ 按键转人工
    5. 转人工后，由人工坐席接单 → 人工对话 → 人工办结

注意:
- 需要服务已启动（uvicorn main:app --host 0.0.0.0 --port 8000）
- 或者使用 TestClient 直接在进程内运行（不启动服务）
"""

import sys
import os
import uuid

try:
    import readline  # 命令行历史回溯（非必须）
except ImportError:
    pass

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional
import httpx

from config import settings
from tests.helpers import (
    simulate_call_started,
    simulate_ivr_key,
    simulate_dtmf,
    simulate_dialogue,
    simulate_hangup,
    get_agents,
    update_agent_status,
    agent_accept_order,
    agent_complete_order,
    simulate_human_dialogue,
)

BASE_URL = "http://localhost:8000"


class IVRSimulator:
    """交互式 IVR 命令行模拟器"""

    def __init__(self):
        self.client = httpx.Client(timeout=300)
        self.conversation_id = f"sim-{uuid.uuid4().hex[:8]}"
        self.phone: Optional[str] = None
        self.order_id: Optional[int] = None
        self.transferred: bool = False
        self.agent_id: Optional[int] = None

    def print_banner(self):
        print("\n" + "=" * 60)
        print("📞 市场监督管理局 IVR 交互式模拟器")
        print("=" * 60)
        print("欢迎语：您好，这里是大东区市场监督管理局，请按键选择：")
        print("  [1] 企业咨询")
        print("  [2] 投诉举报")
        print("  [0] 直接转人工服务")
        print("-" * 60)

    def get_input(self, prompt: str) -> str:
        """获取用户输入"""
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 退出模拟器")
            sys.exit(0)

    def step_ivr_menu(self) -> str:
        """第一步：IVR菜单按键选择"""
        while True:
            key = self.get_input("\n请按键选择 [1/2/0]: ")
            if key in ("1", "2", "0"):
                return key
            print("❌ 无效选择，请输入 1、2 或 0")

    def step_call_started(self, phone: str):
        """模拟来电接入"""
        self.phone = phone
        print(f"\n📞 来电接入：号码 {phone}，conversation_id = {self.conversation_id}")
        resp = simulate_call_started(
            self.client, self.conversation_id, phone,
            base_url=BASE_URL
        )
        if resp.get("code") != 200:
            print(f"❌ CallStarted 失败: {resp}")
            sys.exit(1)

    def start_ivr_flow(self, key: str):
        """根据按键启动对应流程"""
        print(f"\n🔘 按下按键 {key}")
        resp = simulate_ivr_key(
            self.client, self.conversation_id, key,
            base_url=BASE_URL
        )
        if resp.get("code") != 200:
            print(f"❌ IvrKeyPressed 失败: {resp}")
            sys.exit(1)

        # 查询工单 ID
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from database.models import WorkOrder

        engine = create_engine(settings.pg_url)
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        order = db.query(WorkOrder).filter(
            WorkOrder.conversation_id == self.conversation_id
        ).first()
        db.close()

        if not order:
            print("⚠️  工单未创建（直接转人工可能不需要？）")
            self.order_id = None
        else:
            self.order_id = order.order_id
            print(f"✅ 工单已创建，ID = {self.order_id}")

        if key == "0":
            # 直接转人工
            print("\n➡️  IVR直接转人工流程")
            self.transferred = True

    def ensure_agent_online(self) -> int:
        """确保至少有一个人工坐席在线，返回坐席 ID"""
        resp = get_agents(self.client, base_url=BASE_URL)
        agents = resp.get("data", [])
        if not agents:
            print("❌ 数据库中没有人工坐席，请先运行 python -m database.seed_data")
            sys.exit(1)

        # 取第一个坐席上线
        agent = agents[0]
        if agent["agent_status"] != 2:
            print(f"\nℹ️  将坐席 {agent['agent_name']}（ID={agent['agent_id']}）设置为在线")
            update_agent_status(
                self.client, agent["agent_id"], 2,
                ccc_agent_id=agent["ccc_agent_id"]
            )

        self.agent_id = agent["agent_id"]
        print(f"✅ 人工坐席 {agent['agent_name']} 已在线")
        return agent["agent_id"]

    def chat_with_ai(self):
        """与智能机器人对话，支持随时按键 0 转人工"""
        if not self.order_id:
            print("❌ 工单不存在，无法开始AI对话")
            return

        print("\n" + "=" * 60)
        print("🤖 智能机器人对话已开始，请输入问题。")
        print("💡 提示：输入 '0'（单独一行）= 按键转人工；输入 'quit' = 结束通话")
        print("=" * 60)

        while True:
            user_input = self.get_input("\n[你] ")

            if user_input.lower() in ("quit", "exit", "q"):
                # 用户挂断
                print("📞 用户挂断，结束通话")
                simulate_hangup(self.client, self.conversation_id, base_url=BASE_URL)
                break

            if user_input == "0":
                # DTMF按键转人工
                print("\n🔘 按下按键 0 → 触发转人工")
                resp = simulate_dtmf(
                    self.client, self.conversation_id, "0",
                    base_url=BASE_URL
                )
                print(f"✅ DTMF事件已发送，转人工流程已启动")
                self.transferred = True
                break

            # 调用AI对话
            resp = simulate_dialogue(
                self.client, self.order_id, user_input,
                base_url=BASE_URL
            )

            if resp.get("code") != 200:
                print(f"❌ AI对话失败: {resp}")
                continue

            answer = resp["data"].get("answer", "无回答")
            action = resp["data"].get("action")

            print(f"\n[机器人] {answer}")

            if action == "transfer_to_agent":
                reason = resp["data"].get("reason", "机器人要求转人工")
                print(f"\n➡️  机器人自动触发转人工: {reason}")
                self.transferred = True
                break

    def chat_with_human(self):
        """人工坐席与用户对话（模拟）"""
        if not self.order_id or not self.agent_id:
            print("❌ 工单或坐席ID无效")
            return

        print("\n" + "=" * 60)
        print("👷 人工坐席对话模式")
        print("格式：直接输入坐席说的话，对话完成后输入 'done' 办结工单")
        print("=" * 60)

        # 坐席接单
        accept_resp = agent_accept_order(
            self.client, self.agent_id,
            base_url=BASE_URL
        )
        if accept_resp["code"] != 200:
            print(f"❌ 接单失败: {accept_resp}")
            return

        print(f"✅ 坐席已接单，开始对话")

        while True:
            msg = self.get_input("\n[人工坐席] ")
            if msg.lower() == "done":
                break

            # 保存人工坐席发言
            simulate_human_dialogue(
                self.client, self.order_id, msg,
                role="worker", agent_id=self.agent_id,
                base_url=BASE_URL
            )

            # 提示用户发言
            user_msg = self.get_input("[用户] ")
            if user_msg:
                simulate_human_dialogue(
                    self.client, self.order_id, user_msg,
                    role="user", agent_id=self.agent_id,
                    base_url=BASE_URL
                )

        # 人工办结
        complete_resp = agent_complete_order(
            self.client, self.order_id, self.agent_id,
            base_url=BASE_URL
        )
        if complete_resp["code"] == 200:
            biz_summary = complete_resp["data"].get("biz_summary", "")
            print(f"\n✅ 工单已办结，LLM生成业务摘要:")
            print(f"   {biz_summary}")
        else:
            print(f"❌ 办结失败: {complete_resp}")

    def run(self):
        """运行完整交互式流程"""
        self.print_banner()

        # 输入来电号码
        default_phone = "13900139000"
        phone_input = self.get_input(f"请输入来电号码 [{default_phone}]: ")
        phone = phone_input or default_phone

        # 模拟来电
        self.step_call_started(phone)

        # IVR菜单
        key = self.step_ivr_menu()

        # 启动对应流程
        self.start_ivr_flow(key)

        if key in ("1", "2") and self.order_id:
            # 进入AI对话
            self.chat_with_ai()
        else:
            # 直接转人工
            self.ensure_agent_online()
            self.chat_with_human()
            return

        if self.transferred and self.order_id:
            print("\n" + "=" * 60)
            print("➡️  正在转人工，请确保至少有一个在线坐席...")
            print("=" * 60)
            self.ensure_agent_online()
            self.chat_with_human()

        print("\n🎉 全流程模拟完成！")


def main():
    """主入口"""
    # 检查环境
    if not settings.DASHSCOPE_API_KEY:
        print("⚠️  警告: DASHSCOPE_API_KEY 未配置，LLM 摘要生成可能失败")

    simulator = IVRSimulator()
    simulator.run()


if __name__ == "__main__":
    main()
