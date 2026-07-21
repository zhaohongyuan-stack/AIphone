"""
Java 后端 API 客户端。

Python 服务端通过此客户端调用 Java 后端的 REST API 完成所有数据库写操作，
不再直接操作 work_order / dialogue_detail / agent_info 三张主表。

字段命名约定：Python 端用蛇形（snake_case），Java 端用驼峰（camelCase），
本客户端负责自动转换。
"""

import httpx
import logging
from typing import Optional
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)


class JavaApiClient:
    """Java 后端 API 客户端单例。"""

    def __init__(self):
        self._base_url: str = ""
        self._client: Optional[httpx.Client] = None

    @property
    def base_url(self) -> str:
        if not self._base_url:
            self._base_url = getattr(settings, "JAVA_API_BASE_URL", "http://java-backend:8080")
        return self._base_url

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0),
            )
        return self._client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    # ────────────── 内部工具 ──────────────

    def _post(self, path: str, json_data: dict) -> dict:
        """POST 请求，返回 response.data。失败抛异常。"""
        try:
            resp = self.client.post(path, json=json_data)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 200:
                raise RuntimeError(f"Java API 返回错误: {body}")
            return body.get("data", {})
        except httpx.HTTPError as e:
            logger.error(f"Java API POST {path} 失败: {e}")
            raise

    def _patch(self, path: str, json_data: dict) -> dict:
        """PATCH 请求。"""
        try:
            resp = self.client.patch(path, json=json_data)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 200:
                raise RuntimeError(f"Java API 返回错误: {body}")
            return body.get("data", {})
        except httpx.HTTPError as e:
            logger.error(f"Java API PATCH {path} 失败: {e}")
            raise

    def _put(self, path: str, json_data: dict) -> dict:
        """PUT 请求。"""
        try:
            resp = self.client.put(path, json=json_data)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 200:
                raise RuntimeError(f"Java API 返回错误: {body}")
            return body.get("data", {})
        except httpx.HTTPError as e:
            logger.error(f"Java API PUT {path} 失败: {e}")
            raise

    def _get(self, path: str, params: dict = None) -> dict:
        """GET 请求。"""
        try:
            resp = self.client.get(path, params=params)
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 200:
                raise RuntimeError(f"Java API 返回错误: {body}")
            return body.get("data", {})
        except httpx.HTTPError as e:
            logger.error(f"Java API GET {path} 失败: {e}")
            raise

    # ────────────── 工单接口 ──────────────

    def create_order(
        self,
        phone: str,
        conversation_id: str,
        instance_id: str,
        order_type: int = 1,
    ) -> dict:
        """创建工单。对应 Java POST /api/orders。

        Returns: {"orderId": Long, "orderStatus": int, "createdTime": "yyyy-MM-dd HH:mm:ss"}
        """
        data = {
            "phone": phone,
            "conversationId": conversation_id,
            "instanceId": instance_id,
            # order_type 由 Java 端默认为 1（咨询），如需指定可在 Java 端扩展 OrderCreateReq
        }
        result = self._post("/api/orders", data)
        logger.info(f"通过 Java API 创建工单: conversationId={conversation_id}, result={result}")
        return result

    def update_order(self, order_id: int, **kwargs) -> dict:
        """更新工单。对应 Java PATCH /api/orders/{order_id}。

        支持的字段（蛇形参数名自动转驼峰）：
        ent_name, ent_address, ent_cerdit, contact_name, phone, order_type,
        order_status, agent_id, biz_summary, ai_failure_note, ai_solved,
        summary_confirmed, call_start_time, call_end_time

        Returns: {"orderId": Long, "updateTime": "yyyy-MM-dd HH:mm:ss"}
        """
        # 蛇形 → 驼峰映射
        snake_to_camel = {
            "ent_name": "entName",
            "ent_address": "entAddress",
            "ent_cerdit": "entCerdit",
            "contact_name": "contactName",
            "phone": "phone",
            "order_type": "orderType",
            "order_status": "orderStatus",
            "agent_id": "agentId",
            "biz_summary": "bizSummary",
            "ai_failure_note": "aiFailureNote",
            "ai_solved": "aiSolved",
            "summary_confirmed": "summaryConfirmed",
            "call_start_time": "callStartTime",
            "call_end_time": "callEndTime",
        }
        data = {}
        for k, v in kwargs.items():
            if v is None:
                continue
            camel_key = snake_to_camel.get(k, k)
            if isinstance(v, datetime):
                data[camel_key] = v.strftime("%Y-%m-%d %H:%M:%S")
            else:
                data[camel_key] = v

        if not data:
            logger.warning(f"update_order 无有效字段: orderId={order_id}")
            return {}

        result = self._patch(f"/api/orders/{order_id}", data)
        logger.info(f"通过 Java API 更新工单: orderId={order_id}, fields={list(data.keys())}")
        return result

    def get_order(self, order_id: int) -> dict:
        """查询工单详情。对应 Java GET /api/orders/{order_id}。"""
        return self._get(f"/api/orders/{order_id}")

    def get_orders_by_phone(self, phone: str, limit: int = 5) -> dict:
        """按电话查历史工单。对应 Java GET /api/orders/by-phone?phone=&limit=。"""
        return self._get("/api/orders/by-phone", params={"phone": phone, "limit": limit})

    def confirm_order(self, order_id: int, order_status: int) -> dict:
        """工单状态变更。对应 Java PUT /api/orders/{order_id}/confirm。"""
        return self._put(f"/api/orders/{order_id}/confirm", {"orderStatus": order_status})

    def dispatch_order(self, order_id: int) -> dict:
        """工单流转推送（办结 + call_end_time）。对应 Java POST /api/orders/{order_id}/dispatch。"""
        result = self._post(f"/api/orders/{order_id}/dispatch", {})
        logger.info(f"通过 Java API 流转工单: orderId={order_id}")
        return result

    # ────────────── 对话接口 ──────────────

    def save_dialogue(self, order_id: int, content: str, role: str) -> dict:
        """保存对话明细（直接落库）。对应 Java POST /api/dialogue。

        Args:
            order_id: 工单 ID
            content: 文本内容
            role: 发言角色（AI/user/worker/ivr）

        Returns: {"diaId": Long, "msgTime": "yyyy-MM-dd HH:mm:ss"}
        """
        data = {"orderId": order_id, "content": content, "role": role}
        result = self._post("/api/dialogue", data)
        return result

    # ────────────── 坐席接口 ──────────────

    def update_agent_status(self, agent_id: int, agent_status: int) -> dict:
        """更新坐席状态。对应 Java PUT /api/agent/status。"""
        return self._put("/api/agent/status", {"agentId": agent_id, "agentStatus": agent_status})

    def list_agents(self) -> list:
        """坐席列表。对应 Java GET /api/agent/list。"""
        return self._get("/api/agent/list")

    def accept_order(self, agent_id: int, order_id: int) -> dict:
        """坐席接单。对应 Java POST /api/agent/accept。

        Returns: {"orderId": Long, "agentId": Long, "agentStatus": int, "callStartTime": "..."}
        """
        result = self._post("/api/agent/accept", {"agentId": agent_id, "orderId": order_id})
        logger.info(f"通过 Java API 坐席接单: agentId={agent_id}, orderId={order_id}")
        return result

    def complete_order(self, order_id: int, agent_id: int, manual_summary: str = None) -> dict:
        """坐席办结。对应 Java POST /api/agent/complete。

        Returns: {"orderId": Long, "agentId": Long, "agentStatus": int, "bizSummary": "...", "callEndTime": "..."}
        """
        data = {"orderId": order_id, "agentId": agent_id}
        if manual_summary:
            data["manualSummary"] = manual_summary
        result = self._post("/api/agent/complete", data)
        logger.info(f"通过 Java API 坐席办结: agentId={agent_id}, orderId={order_id}")
        return result


# 全局单例
java_client = JavaApiClient()
