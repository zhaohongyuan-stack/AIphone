"""
理解 Skill + 填写 Skill (LLM Agent)
- 理解Skill: 从对话中提取工单结构化字段
- 填写Skill: 检查缺失字段，生成追问话术，最终生成工单
"""
import json
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class LLMSkill:
    """基于通义千问的 Skill 实现"""

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.LLM_MODEL

    def _chat(self, system: str, user: str, temperature: float = 0.1) -> str:
        """调用通义千问对话接口"""
        try:
            resp = httpx.post(
                f"{self.BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": temperature,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return ""

    # ════════════════════════════════════════════════════════════
    #  理解 Skill
    # ════════════════════════════════════════════════════════════

    def understand(self, history: list) -> dict:
        """
        从对话历史中提取工单结构化字段
        返回: {
            ent_name, ent_address, ent_credit,
            contact_name, phone,
            order_type, biz_summary,
            missing_fields: [...]
        }
        """
        sys_prompt = """你是市场监督管理局智能助手的"理解Skill"。
从用户与AI机器人的对话中提取工单所需的结构化信息。

输出严格的JSON格式：
{
  "ent_name": "企业名称（未知为null）",
  "ent_address": "经营地址（未知为null）",
  "ent_credit": "统一社会信用代码（未知为null）",
  "contact_name": "联系人姓名（未知为null）",
  "phone": "联系电话（未知为null）",
  "order_type": "0-转播/1-咨询/2-投诉/3-回访，整数",
  "biz_summary": "业务诉求摘要，一句话描述",
  "missing_fields": ["缺失字段名1", "缺失字段名2"]
}

只输出JSON，不要任何解释。"""

        history_text = "\n".join(
            f"[{m['role']}] {m['content']}" for m in history
        )
        result = self._chat(sys_prompt, history_text)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"missing_fields": ["解析失败"]}

    # ════════════════════════════════════════════════════════════
    #  填写 Skill
    # ════════════════════════════════════════════════════════════

    def fill(self, extracted: dict, history: list) -> dict:
        """
        根据理解Skill的输出，检查缺失字段并生成追问话术
        返回: {
            action: "ask" | "complete",
            question: "追问话术（action=ask时）",
            work_order: {最终工单数据（action=complete时）}
        }
        """
        missing = extracted.get("missing_fields", [])
        if not missing:
            return {
                "action": "complete",
                "work_order": {
                    "ent_name": extracted.get("ent_name"),
                    "ent_address": extracted.get("ent_address"),
                    "ent_credit": extracted.get("ent_credit"),
                    "contact_name": extracted.get("contact_name"),
                    "phone": extracted.get("phone"),
                    "order_type": extracted.get("order_type", 1),
                    "biz_summary": extracted.get("biz_summary"),
                },
            }

        sys_prompt = """你是市场监督管理局智能助手的"填写Skill"。
根据理解Skill提取的结果，发现工单缺少必要字段。
请生成一句自然、礼貌的追问话术，向用户询问缺失的信息。

字段说明：
- ent_name: 企业名称
- ent_address: 经营地址
- ent_credit: 统一社会信用代码
- contact_name: 联系人姓名
- phone: 联系电话

输出JSON格式：
{
  "action": "ask",
  "question": "追问话术"
}
只输出JSON。"""

        user_msg = f"已提取信息：{json.dumps(extracted, ensure_ascii=False)}\n缺失字段：{missing}"
        result = self._chat(sys_prompt, user_msg)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {
                "action": "ask",
                "question": f"请问您能补充一下{('、'.join(missing))}吗？",
            }


    # ════════════════════════════════════════════════════════════
    #  摘要生成
    # ════════════════════════════════════════════════════════════

    def summarize(self, history: list, role: str) -> str:
        """
        从对话历史中生成摘要
        role = "ai" → 生成 ai_failure_note（AI对话摘要，帮助人工快速了解诉求）
        role = "human" → 生成 biz_summary（人工处理总结）
        """
        if not history:
            return ""

        if role == "ai":
            sys_prompt = """你是市场监督管理局智能助手的"AI对话摘要生成器"。
请根据用户与AI机器人的对话历史，生成一段简洁的摘要，帮助人工坐席快速了解用户诉求。

要求：
1. 200字以内
2. 包含：用户核心诉求、已提供的关键信息（企业名称/地址/联系方式等）、AI未解决的问题点
3. 客观陈述，不要添加未在对话中出现的信息

只输出摘要内容，不要任何前缀或解释。"""
        else:
            sys_prompt = """你是市场监督管理局智能助手的"人工处理摘要生成器"。
请根据人工坐席与用户的对话历史，生成一段简洁的处理总结，作为工单的 biz_summary。

要求：
1. 200字以内
2. 包含：用户诉求、人工坐席的处理方案、最终结果
3. 客观陈述

只输出摘要内容，不要任何前缀或解释。"""

        history_text = "\n".join(
            f"[{m['role']}] {m['content']}" for m in history
        )
        result = self._chat(sys_prompt, history_text, temperature=0.3)
        return result.strip()


# 全局单例
llm_skill = LLMSkill()
