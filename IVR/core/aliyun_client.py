"""
阿里云 SDK 封装：CCC 云联络中心 + Beebot 智能对话机器人
统一提供业务层调用的接口

注意：阿里云 Python SDK 是可选的。未安装时，所有方法返回模拟数据，系统仍可正常运行。
安装命令：
  pip install aliyun-python-sdk-core aliyun-python-sdk-ccc
  pip install alibabacloud_chatbot20220408

Beebot 对话通过官方 Chat API（Chatbot SDK）调用。
"""
import hashlib
import json
import logging
import time
import uuid
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── 尝试导入阿里云 SDK（CCC 部分）──────────────────────────────
try:
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkcore.acs_exception.exceptions import ServerException, ClientException
    ACS_AVAILABLE = True
except ImportError:
    AcsClient = None
    ACS_AVAILABLE = False
    logger.warning("aliyun-python-sdk-core 未安装，阿里云 CCC 接口将不可用。"
                   "安装: pip install aliyun-python-sdk-core aliyun-python-sdk-ccc")

try:
    from aliyunsdkccc.request.v20200701 import (
        PollUserStatusRequest, GetConversationDetailRequest,
        GetCallDetailRecordRequest, BlindTransferRequest,
        SignInGroupRequest, SignOutGroupRequest, ReadyForServiceRequest,
        TakeBreakRequest
    )
    CCC_AVAILABLE = True
except ImportError:
    CCC_AVAILABLE = False
    logger.warning("aliyun-python-sdk-ccc 未安装。"
                   "安装: pip install aliyun-python-sdk-ccc")

# ── 尝试导入 Chatbot SDK（Beebot 部分）────────────────────────
try:
    from alibabacloud_chatbot20220408.client import Client as ChatbotClient
    from alibabacloud_chatbot20220408 import models as chatbot_models
    from alibabacloud_tea_openapi import models as open_api_models
    CHATBOT_AVAILABLE = True
except ImportError:
    CHATBOT_AVAILABLE = False
    logger.warning("alibabacloud_chatbot20220408 未安装，Beebot 对话将不可用。"
                   "安装: pip install alibabacloud_chatbot20220408")

try:
    from alibabacloud_openapi_util.client import Client as OpenApiUtilClient
    from alibabacloud_tea_util import models as util_models
    SSE_UTIL_AVAILABLE = True
except ImportError:
    SSE_UTIL_AVAILABLE = False
    logger.warning("alibabacloud_openapi_util 未安装，Beebot SSE 接口将不可用。"
                   "安装: pip install alibabacloud_openapi_util")

from config import settings


class AliyunClient:
    """阿里云统一客户端"""

    def __init__(self):
        self.available = ACS_AVAILABLE and settings.ALIYUN_ACCESS_KEY_ID
        if self.available:
            self.acs_client = AcsClient(
                settings.ALIYUN_ACCESS_KEY_ID,
                settings.ALIYUN_ACCESS_KEY_SECRET,
                settings.ALIYUN_REGION_ID
            )
        else:
            self.acs_client = None

        # Chatbot SDK 客户端（延迟初始化，首次调用时创建）
        self._chatbot_client = None
        # SSE 流式会话凭证缓存（通义版，有效期 2 小时）
        self._sse_credentials: Optional[dict] = None
        self._sse_expire: float = 0

    def _ccc_ok(self) -> bool:
        return self.available and CCC_AVAILABLE

    def _beebot_ok(self) -> bool:
        """Beebot 需配置 AccessKey + InstanceId + SDK 可用"""
        return bool(
            settings.ALIYUN_ACCESS_KEY_ID
            and settings.BEEBOT_INSTANCE_ID
            and self.available
            and CHATBOT_AVAILABLE
            and SSE_UTIL_AVAILABLE
        )

    def _get_chatbot_client(self):
        """获取 Chatbot SDK 客户端（单例）"""
        if self._chatbot_client:
            return self._chatbot_client

        config = open_api_models.Config(
            access_key_id=settings.ALIYUN_ACCESS_KEY_ID,
            access_key_secret=settings.ALIYUN_ACCESS_KEY_SECRET,
            region_id=settings.ALIYUN_REGION_ID,
            endpoint=f"chatbot.{settings.ALIYUN_REGION_ID}.aliyuncs.com",
        )
        self._chatbot_client = ChatbotClient(config)
        return self._chatbot_client

    # ════════════════════════════════════════════════════════════
    #  CCC 云联络中心
    # ════════════════════════════════════════════════════════════

    def poll_user_status(self, user_id: str) -> dict:
        """轮询坐席状态"""
        if not self._ccc_ok():
            logger.debug(f"[SIMULATE] PollUserStatus: {user_id}")
            return {"Data": {"UserState": "READY", "CallType": "OUTBOUND"}}
        req = PollUserStatusRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_UserId(user_id)
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp)

    def get_conversation_detail(self, contact_id: str) -> list:
        """获取对话详情（语音转写）"""
        if not self._ccc_ok():
            logger.debug(f"[SIMULATE] GetConversationDetail: {contact_id}")
            return []
        req = GetConversationDetailRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_ContactId(contact_id)
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp).get("Phrases", [])

    def get_call_detail(self, contact_id: str) -> dict:
        """获取通话详情"""
        if not self._ccc_ok():
            logger.debug(f"[SIMULATE] GetCallDetailRecord: {contact_id}")
            return {"Data": {"ContactDisposition": "UserHangup"}}
        req = GetCallDetailRecordRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_ContactId(contact_id)
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp)

    def blind_transfer(self, transferee: str, user_id: str = None,
                       timeout: int = 60) -> dict:
        """直接转接通话"""
        if not self._ccc_ok():
            logger.debug(f"[SIMULATE] BlindTransfer → {transferee}")
            return {"Code": "200", "Message": "OK"}
        req = BlindTransferRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_Transferee(transferee)
        if user_id:
            req.set_UserId(user_id)
        req.set_TimeoutSeconds(timeout)
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp)

    def sign_in_group(self, user_id: str, device_id: str,
                      skill_group_ids: list = None) -> dict:
        """坐席签入技能组"""
        if not self._ccc_ok():
            logger.debug(f"[SIMULATE] SignInGroup: {user_id}")
            return {"Code": "200"}
        req = SignInGroupRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_UserId(user_id)
        req.set_DeviceId(device_id)
        if skill_group_ids:
            req.set_SignedSkillGroupIdList(json.dumps(skill_group_ids))
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp)

    def sign_out_group(self, user_id: str) -> dict:
        """坐席签出"""
        if not self._ccc_ok():
            logger.debug(f"[SIMULATE] SignOutGroup: {user_id}")
            return {"Code": "200"}
        req = SignOutGroupRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_UserId(user_id)
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp)

    def ready_for_service(self, user_id: str) -> dict:
        """坐席就绪"""
        if not self._ccc_ok():
            return {"Code": "200"}
        req = ReadyForServiceRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_UserId(user_id)
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp)

    def take_break(self, user_id: str, break_code: str = "") -> dict:
        """坐席小休"""
        if not self._ccc_ok():
            return {"Code": "200"}
        req = TakeBreakRequest()
        req.set_InstanceId(settings.CCC_INSTANCE_ID)
        req.set_UserId(user_id)
        if break_code:
            req.set_BreakCode(break_code)
        resp = self.acs_client.do_action_with_exception(req)
        return json.loads(resp)

    # ════════════════════════════════════════════════════════════
    #  Beebot 智能对话机器人（通义版）— SSE 流式会话 API
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _get_sign(stream_secret: str, timestamp: str) -> str:
        """计算会话接口签名：MD5(streamSecret={secret}&timestamp={ts})"""
        text = f"streamSecret={stream_secret}&timestamp={timestamp}"
        return hashlib.md5(text.encode("utf-8")).hexdigest()

    def _get_sse_credentials(self) -> dict:
        """
        获取 SSE 流式会话凭证（通义版）
        调用 ApplyForStreamAccessToken 接口，返回 {AccessToken, ChannelId, StreamSecret}
        凭证缓存 2 小时
        """
        if self._sse_credentials and time.time() < self._sse_expire:
            return self._sse_credentials

        client = self._get_chatbot_client()
        params = open_api_models.Params(
            action="ApplyForStreamAccessToken",
            version="2022-04-08",
            protocol="HTTPS",
            method="POST",
            auth_type="AK",
            style="RPC",
            pathname="/",
            req_body_type="json",
            body_type="json",
        )
        queries = {}
        if settings.BEEBOT_AGENT_KEY:
            queries["AgentKey"] = settings.BEEBOT_AGENT_KEY
        runtime = util_models.RuntimeOptions()
        request = open_api_models.OpenApiRequest(
            query=OpenApiUtilClient.query(queries)
        )
        res = client.call_api(params, request, runtime)
        body = res["body"]

        self._sse_credentials = {
            "AccessToken": body["AccessToken"],
            "ChannelId": body["ChannelId"],
            "StreamSecret": body["StreamSecret"],
        }
        self._sse_expire = time.time() + 7100  # 提前 100s 过期，留余量
        logger.debug(f"[Beebot SSE] 获取凭证成功, ChannelId={body['ChannelId']}")
        return self._sse_credentials

    def begin_session(self, vendor_params: dict = None) -> dict:
        """
        开启 Beebot 会话（生成 SessionId）
        返回: {SessionId, Answer}
        """
        session_id = str(uuid.uuid4())

        if not self._beebot_ok():
            logger.debug(f"[SIMULATE] Beebot begin_session: {vendor_params}")
            return {
                "SessionId": session_id,
                "Answer": "您好，欢迎致电大东区市场监督管理局，请问有什么可以帮您？",
            }

        return self._chat_sse(session_id, "", vendor_params or {})

    def dialogue(self, session_id: str, utterance: str,
                 vendor_params: dict = None) -> dict:
        """
        Beebot 对话（通义版 SSE 流式）
        返回: {Answer, Type, StreamEnd, SessionId, Commands}
        - Type: Direct(直接回答) / Clarify(澄清反问)
        - Commands: sysToAgent(转人工指令)
        """
        if not self._beebot_ok():
            logger.debug(f"[SIMULATE] Beebot dialogue: {utterance[:30]}...")
            return {
                "Answer": '您好，您的问题已收到，请稍候。如需人工服务请说"转人工"。',
                "Type": "Direct",
                "StreamEnd": True,
                "SessionId": session_id,
                "Commands": [],
            }

        return self._chat_sse(session_id, utterance, vendor_params or {})

    def end_session(self, session_id: str) -> dict:
        """结束 Beebot 会话（无需调用API，SessionId自然过期）"""
        return {"Code": "200", "Message": "Session ended"}

    def _chat_sse(self, session_id: str, utterance: str,
                  vendor_params: dict) -> dict:
        """
        通过 SSE 流式会话 API 进行对话（通义版）
        utterance 为空时触发开场白
        """
        try:
            creds = self._get_sse_credentials()

            # 生成签名
            timestamp = str(int(time.time() * 1000))
            sign = self._get_sign(creds["StreamSecret"], timestamp)

            # 构建 SSE URL
            sse_url = (
                f"https://alime-ws.aliyuncs.com/sse/paas4Json/"
                f"{creds['AccessToken']}/{creds['ChannelId']}/{sign}/{timestamp}"
            )

            # 构建请求体
            message_id = str(uuid.uuid4())
            inner_data = {
                "InstanceId": settings.BEEBOT_INSTANCE_ID,
                "Utterance": utterance if utterance else "你好",
                "SessionId": session_id,
                "SenderId": vendor_params.get("phone", "caller"),
            }
            if vendor_params:
                inner_data["VendorParam"] = json.dumps(
                    vendor_params, ensure_ascii=False
                )

            payload = {
                "messageId": message_id,
                "action": "TongyiBeebotChat",
                "version": "2022-04-08",
                "data": [{
                    "type": "JSON_TEXT",
                    "value": json.dumps(inner_data, ensure_ascii=False),
                }],
            }

            logger.debug(
                f"[Beebot SSE] 调用: session={session_id} "
                f"utterance={utterance[:50] if utterance else '(开场白)'}"
            )

            # 收集 SSE 流式响应
            answer = ""
            result_type = "Direct"
            commands = []
            returned_session_id = session_id

            with httpx.stream(
                "POST", sse_url, json=payload, timeout=120
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    try:
                        event = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    if not event.get("success"):
                        continue

                    for item in event.get("data") or []:
                        if item.get("type") != "JSON_TEXT":
                            continue
                        try:
                            inner = json.loads(item["value"])
                        except (json.JSONDecodeError, TypeError):
                            continue

                        if inner.get("SessionId"):
                            returned_session_id = inner["SessionId"]

                        msg_body = inner.get("MessageBody", {})
                        if msg_body.get("Type"):
                            result_type = msg_body["Type"]

                        # 更新答案文本（SSE每次返回完整累积文本，直接替换而非累加）
                        if msg_body.get("Type") == "Direct":
                            direct = msg_body.get("DirectMessageBody", {})
                            sentences = direct.get("SentenceList") or []
                            if sentences:
                                answer = "".join(s.get("Content", "") for s in sentences)
                        elif msg_body.get("Type") == "Clarify":
                            clarify = msg_body.get("ClarifyMessageBody", {})
                            answer = clarify.get("ClarifyContent", answer)

                        # 检查转人工指令
                        cmds = inner.get("Commands") or msg_body.get("Commands") or {}
                        if cmds and "sysToAgent" in cmds:
                            agent_info = cmds["sysToAgent"]
                            if isinstance(agent_info, str):
                                try:
                                    agent_info = json.loads(agent_info)
                                except json.JSONDecodeError:
                                    pass
                            reason = (
                                agent_info.get("toAgentReason", "机器人转人工")
                                if isinstance(agent_info, dict)
                                else str(agent_info)
                            )
                            commands.append({
                                "Type": "Transfer",
                                "Reason": reason,
                            })

            return {
                "Answer": answer or "抱歉，我没有理解您的意思，请重新描述。",
                "Type": result_type,
                "StreamEnd": True,
                "SessionId": returned_session_id,
                "Commands": commands,
            }

        except Exception as e:
            logger.error(f"Beebot SSE 调用失败: {e}")
            return {
                "Answer": "抱歉，系统暂时无法响应，正在为您转接人工客服。",
                "Type": "Direct",
                "StreamEnd": True,
                "SessionId": session_id,
                "Commands": [{"Type": "Transfer", "Reason": "API调用失败"}],
            }


# 全局单例
aliyun = AliyunClient()
