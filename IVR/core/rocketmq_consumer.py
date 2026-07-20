"""
RocketMQ 5.x 消费者：消费阿里云 CCC 事件推送消息

CCC 事件推送通过 RocketMQ 5.x gRPC SDK 消费。
本模块在后台线程中使用 SimpleConsumer 长轮询拉取消息，
解析后路由到 routes.py 中的事件处理器（与 /api/ccc/callback 共用）。

依赖: rocketmq-python-client (Apache RocketMQ 5.x gRPC SDK，纯 Python，Windows 友好)
安装: pip install rocketmq-python-client==5.1.1
"""
import json
import logging
import threading
import time

from config import settings
from core import logger as log

logger = logging.getLogger(__name__)

# 消费者线程引用
_consumer_thread: threading.Thread | None = None
_stop_event = threading.Event()
_simple_consumer = None  # 全局引用，用于 shutdown


def _is_configured() -> bool:
    """检查 RocketMQ 配置是否完整"""
    return bool(
        settings.ROCKETMQ_ENDPOINT
        and settings.ROCKETMQ_INSTANCE_ID
        and settings.ROCKETMQ_TOPIC
        and settings.ROCKETMQ_GROUP_ID
        and settings.ROCKETMQ_ACCESS_KEY
        and settings.ROCKETMQ_ACCESS_SECRET
    )


def _consume_loop():
    """
    消费主循环（在后台线程中运行）
    1. 创建 SimpleConsumer 并启动
    2. 长轮询拉取消息
    3. 解析消息体 → 路由到事件处理器
    4. 确认消费（ack）
    """
    global _simple_consumer

    # 延迟导入，避免循环依赖（routes.py 尚未加载完成时不会触发）
    from api.routes import _CCC_EVENT_HANDLERS
    from database.models import SessionLocal

    try:
        from rocketmq import (
            ClientConfiguration, Credentials, FilterExpression, SimpleConsumer,
        )
    except ImportError:
        log.error(
            "rocketmq-python-client 未安装，CCC 事件无法消费。"
            "安装: pip install rocketmq-python-client==5.1.1"
        )
        return

    log.info(
        f"RocketMQ 消费者启动: endpoint={settings.ROCKETMQ_ENDPOINT} "
        f"topic={settings.ROCKETMQ_TOPIC} group={settings.ROCKETMQ_GROUP_ID}"
    )

    # 初始化客户端
    credentials = Credentials(
        settings.ROCKETMQ_ACCESS_KEY,
        settings.ROCKETMQ_ACCESS_SECRET,
    )
    # 第三个参数是 namespace（即实例ID），公网访问时必须填写
    config = ClientConfiguration(
        settings.ROCKETMQ_ENDPOINT,
        credentials,
        settings.ROCKETMQ_INSTANCE_ID,
    )

    topic = settings.ROCKETMQ_TOPIC
    consumer_group = settings.ROCKETMQ_GROUP_ID

    try:
        _simple_consumer = SimpleConsumer(
            config, consumer_group, {topic: FilterExpression()},
        )
        _simple_consumer.startup()
        log.info("RocketMQ SimpleConsumer 启动成功")
    except Exception as e:
        log.error(f"RocketMQ SimpleConsumer 启动失败: {e}")
        return

    # 长轮询参数
    max_message_num = 32  # 每次最多拉取32条
    invisible_duration = 15  # 消息接收后不可见时间（秒）
    retry_delay = 2
    max_retry_delay = 30

    while not _stop_event.is_set():
        db = None
        try:
            # 长轮询拉取消息
            messages = _simple_consumer.receive(max_message_num, invisible_duration)

            if not messages:
                retry_delay = 2
                continue

            retry_delay = 2  # 有消息则重置退避
            db = SessionLocal()

            for msg in messages:
                try:
                    _process_single_message(msg, db, _CCC_EVENT_HANDLERS)
                except Exception as e:
                    log.error(f"消息处理异常 msg_id={getattr(msg, 'message_id', '?')}: {e}")
                # 确认消费
                try:
                    _simple_consumer.ack(msg)
                except Exception as e:
                    log.info(f"ack 失败（句柄可能超时）: {e}")

        except Exception as e:
            err_str = str(e)
            # 没有消息可消费（正常情况）
            if "no new message" in err_str.lower() or "MessageNotExist" in err_str:
                retry_delay = 2
                continue
            log.error(f"消费循环异常: {e}")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)
        finally:
            if db:
                db.close()

    # 关闭消费者
    try:
        _simple_consumer.shutdown()
    except Exception:
        pass
    log.info("RocketMQ 消费者已停止")


def _process_single_message(msg, db, event_handlers: dict):
    """
    处理单条 CCC 事件消息
    消息体格式与 /api/ccc/callback 的 payload 一致
    """
    body = msg.body
    msg_id = msg.message_id

    # body 可能是 bytes 或 str
    if isinstance(body, bytes):
        body_str = body.decode("utf-8")
    else:
        body_str = str(body)

    # 解析消息体（CCC 推送的是 JSON）
    try:
        payload = json.loads(body_str)
    except (json.JSONDecodeError, TypeError) as e:
        log.error(f"消息体 JSON 解析失败 msg_id={msg_id}: {e} body={body_str[:200]}")
        return

    event_type = payload.get("EventType") or payload.get("eventType", "")
    log.info(f"[RocketMQ] 收到 CCC 事件: type={event_type} msg_id={msg_id}")

    # 幂等去重
    from core import redis_manager as rm
    dedup_key = msg_id or payload.get("EventId", "")
    if dedup_key and not rm.set_event_processed(dedup_key):
        log.info(f"[RocketMQ] 重复事件已跳过: msg_id={msg_id}")
        return

    # 路由到事件处理器
    handler = event_handlers.get(event_type)
    if handler:
        try:
            handler(payload, db)
        except Exception as e:
            log.error(f"事件处理失败 type={event_type}: {e}")
    else:
        log.info(f"[RocketMQ] 未识别的 CCC 事件类型: {event_type}")


def start_consumer():
    """启动 RocketMQ 消费者后台线程"""
    global _consumer_thread

    if not _is_configured():
        log.info("RocketMQ 未配置，跳过消费者启动（CCC 事件将通过 HTTP 回调处理）")
        return

    _stop_event.clear()
    _consumer_thread = threading.Thread(target=_consume_loop, daemon=True)
    _consumer_thread.start()
    log.info("RocketMQ 消费者线程已启动")


def stop_consumer():
    """停止 RocketMQ 消费者"""
    _stop_event.set()
    if _consumer_thread and _consumer_thread.is_alive():
        _consumer_thread.join(timeout=5)
    log.info("RocketMQ 消费者已停止")
