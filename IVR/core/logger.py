"""
终端日志可视化（使用 logging 模块，兼容 uvicorn reload 模式）
"""
import logging
import sys
import time

# ANSI 颜色
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"


# ── 配置 logger ──────────────────────────────────────────────
_logger = logging.getLogger("ivr")
_logger.setLevel(logging.DEBUG)
_logger.propagate = False  # 不传播给 uvicorn 的 root logger

# 防止重复添加 handler
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setLevel(logging.DEBUG)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)


def setup():
    """
    统一配置所有子模块日志，确保调试信息在终端可见。
    在 on_startup 中调用（非 if __name__ 中），确保在 uvicorn reload=True
    的 worker 子进程中执行，否则子模块 DEBUG/INFO 日志会被过滤。
    """
    # 将 root logger 级别设为 DEBUG，并将已有 handler 也设为 DEBUG
    # （uvicorn 子进程已给 root 添加了 INFO 级别的 handler，需覆盖）
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in root.handlers:
        h.setLevel(logging.DEBUG)

    # 确保 ivr logger 正常
    _logger.setLevel(logging.DEBUG)
    for h in _logger.handlers:
        h.setLevel(logging.DEBUG)

    # 显式确保子模块 logger 级别为 DEBUG
    for name in ["core.aliyun_client", "core.knowledge_base",
                 "core.llm_skill", "core.rocketmq_consumer"]:
        logging.getLogger(name).setLevel(logging.DEBUG)


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def banner():
    _logger.info(f"{C.CYAN}{C.BOLD}"
                 "市场监督管理智能语音工单系统 v1.0 启动中..."
                 f"{C.RESET}")


def startup_info(pg_ok: bool, redis_ok: bool, aliyun_ok: bool,
                 slot_count: int, agent_count: int):
    pg = f"{C.GREEN}✅{C.RESET} 已连接" if pg_ok else f"{C.RED}❌ 连接失败{C.RESET}"
    rd = f"{C.GREEN}✅{C.RESET} 已连接" if redis_ok else f"{C.RED}❌ 连接失败{C.RESET}"
    ay = f"{C.GREEN}✅{C.RESET} 已初始化" if aliyun_ok else f"{C.YELLOW}⚠️ 未配置{C.RESET}"
    _logger.info(
        f"{C.CYAN}"
        f"  PostgreSQL  {pg}\n"
        f"  Redis       {rd}\n"
        f"  阿里云SDK    {ay}\n"
        f"  智能坐席槽位: {slot_count} 个\n"
        f"  人工坐席: {agent_count} 人"
        f"{C.RESET}"
    )


def incoming_call(phone: str, order_id: int):
    _logger.info(f"{C.YELLOW}[{_ts()}] 📞 新来电 {phone} → 创建工单 #{order_id}{C.RESET}")


def ivr_route(phone: str, region: str, key: str, order_type: str):
    _logger.info(f"{C.BLUE}[{_ts()}] 🔀 IVR: 归属地={region}, 按键={key}({order_type}){C.RESET}")


def ivr_pending(phone: str):
    _logger.info(f"{C.YELLOW}[{_ts()}] 📞 来电 {phone} → 等待 IVR 按键分流{C.RESET}")


def ivr_transfer_direct():
    _logger.info(f"{C.BLUE}[{_ts()}] 🔀 IVR: 按键=0(转人工) → 直接转人工坐席{C.RESET}")


def slot_assigned(slot_id: int, order_id: int):
    _logger.info(f"{C.GREEN}[{_ts()}] 🤖 智能坐席分配: Slot#{slot_id} → busy (工单#{order_id}){C.RESET}")


def slot_queued(order_id: int, position: int):
    _logger.info(f"{C.YELLOW}[{_ts()}] ⏳ 智能坐席已满，工单#{order_id} 排队(位置#{position}){C.RESET}")


def slot_released(slot_id: int):
    _logger.info(f"{C.GREEN}[{_ts()}] 📤 Slot#{slot_id} 释放 → idle{C.RESET}")


def bot_speak(text: str):
    _logger.info(f"{C.MAGENTA}[{_ts()}] 🤖 [机器人] {text}{C.RESET}")


def user_speak(text: str):
    _logger.info(f"{C.CYAN}[{_ts()}] 💬 [用户] {text}{C.RESET}")


def skill_extract(fields: str):
    _logger.info(f"{C.GRAY}[{_ts()}] 📝 [理解Skill] 提取: {fields}{C.RESET}")


def reject_hit(keyword: str):
    _logger.info(f"{C.RED}[{_ts()}] ⚠️ [拒绝解答] 命中: {keyword} → 触发转人工{C.RESET}")


def transfer_to_agent(reason: str):
    _logger.info(f"{C.YELLOW}[{_ts()}] 🔄 转人工兜底 (原因: {reason}){C.RESET}")


def agent_answer(agent_name: str, order_id: int):
    _logger.info(f"{C.GREEN}[{_ts()}] 👤 [人工坐席] {agent_name} 已接听，弹屏工单#{order_id}{C.RESET}")


def order_completed(order_id: int, duration: int):
    _logger.info(f"{C.GREEN}[{_ts()}] ✅ 工单 #{order_id} 已办结 → 流转推送 (通话时长 {duration}s){C.RESET}")


def order_dispatched(order_id: int):
    _logger.info(f"{C.BLUE}[{_ts()}] 📤 工单 #{order_id} 已推送至后端处理系统{C.RESET}")


def error(msg: str):
    _logger.error(f"{C.RED}[{_ts()}] ❌ 错误: {msg}{C.RESET}")


def info(msg: str):
    _logger.info(f"{C.GRAY}[{_ts()}] ℹ️ {msg}{C.RESET}")
