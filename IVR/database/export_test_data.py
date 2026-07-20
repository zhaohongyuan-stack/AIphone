"""
DB 同事脚本 3/3：导出测试数据为 JSON
- 导出工单、对话明细、坐席
- 导出 Redis 槽位、队列、历史对话
- 可选上传到 OSS（调用 test_oss_uploader）

用法:
    python -m database.export_test_data                       # 导出到本地
    python -m database.export_test_data --upload              # 导出并上传 OSS
    python -m database.export_test_data --output result.json  # 指定输出文件
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import WorkOrder, DialogueDetail, AgentInfo, SessionLocal
from core import redis_manager as rm
from config import settings

import redis


def serialize_datetime(obj):
    """JSON 序列化辅助：处理 datetime"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def export_orders(db) -> list:
    """导出所有工单"""
    orders = db.query(WorkOrder).all()
    return [{
        "order_id": o.order_id,
        "conversation_id": o.conversation_id,
        "instance_id": o.instance_id,
        "phone": o.phone,
        "ent_name": o.ent_name,
        "ent_address": o.ent_address,
        "ent_cerdit": o.ent_cerdit,
        "contact_name": o.contact_name,
        "order_type": o.order_type,
        "order_status": o.order_status,
        "agent_id": o.agent_id,
        "biz_summary": o.biz_summary,
        "ai_failure_note": o.ai_failure_note,
        "ai_solved": o.ai_solved,
        "call_start_time": o.call_start_time.isoformat() if o.call_start_time else None,
        "call_end_time": o.call_end_time.isoformat() if o.call_end_time else None,
        "created_time": o.created_time.isoformat() if o.created_time else None,
        "update_time": o.update_time.isoformat() if o.update_time else None,
    } for o in orders]


def export_dialogues(db) -> list:
    """导出所有对话明细"""
    dialogues = db.query(DialogueDetail).all()
    return [{
        "dia_id": d.dia_id,
        "order_id": d.order_id,
        "content": d.content,
        "role": d.role,
        "msg_time": d.msg_time.isoformat() if d.msg_time else None,
    } for d in dialogues]


def export_agents(db) -> list:
    """导出所有坐席"""
    agents = db.query(AgentInfo).all()
    return [{
        "agent_id": a.agent_id,
        "agent_name": a.agent_name,
        "agent_status": a.agent_status,
        "ccc_agent_id": a.ccc_agent_id,
    } for a in agents]


def export_redis_state() -> dict:
    """导出 Redis 状态"""
    r = redis.from_url(settings.redis_url, decode_responses=True)

    # 槽位状态
    slots = rm.get_all_slots()

    # 排队队列
    queue_length = rm.get_queue_length()
    queue_items = []
    raw_queue = r.lrange("robot:queue", 0, -1)
    for item in raw_queue:
        queue_items.append(json.loads(item))

    # 历史对话（扫描所有 history:* 键）
    histories = {}
    for key in r.scan_iter("history:*"):
        order_id = key.split(":")[1]
        histories[order_id] = rm.get_history(int(order_id))

    # 来电缓存
    pending_calls = {}
    for key in r.scan_iter("call:pending:*"):
        conv_id = key.replace("call:pending:", "")
        pending_calls[conv_id] = r.get(key)

    return {
        "slots": slots,
        "queue": {
            "length": queue_length,
            "items": queue_items,
        },
        "histories": histories,
        "pending_calls": pending_calls,
    }


def export_all() -> dict:
    """导出全部测试数据"""
    db = SessionLocal()
    try:
        orders = export_orders(db)
        dialogues = export_dialogues(db)
        agents = export_agents(db)
    finally:
        db.close()

    redis_state = export_redis_state()

    return {
        "export_time": datetime.now().isoformat(),
        "summary": {
            "orders": len(orders),
            "dialogues": len(dialogues),
            "agents": len(agents),
            "queue_length": redis_state["queue"]["length"],
        },
        "orders": orders,
        "dialogues": dialogues,
        "agents": agents,
        "redis": redis_state,
    }


def main():
    do_upload = "--upload" in sys.argv
    output_file = "test_export.json"

    # 解析 --output 参数
    for i, arg in enumerate(sys.argv):
        if arg == "--output" and i + 1 < len(sys.argv):
            output_file = sys.argv[i + 1]

    print("正在导出测试数据...")
    data = export_all()

    summary = data["summary"]
    print(f"\n导出完成:")
    print(f"  工单:       {summary['orders']} 条")
    print(f"  对话明细:   {summary['dialogues']} 条")
    print(f"  坐席:       {summary['agents']} 条")
    print(f"  排队队列:   {summary['queue_length']} 人")

    if do_upload:
        # 上传到 OSS
        try:
            # 添加 tests 目录到 path 以导入 upload_report
            tests_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "tests"
            )
            sys.path.insert(0, tests_dir)
            from test_oss_uploader import upload_report

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_name = f"test_data_export_{timestamp}.json"
            result = upload_report(data, report_name)

            print(f"\n上传结果: {result['message']}")
            print(f"  位置: {result['location']}")
            if result["fallback"]:
                print(f"  (已降级到本地，配置 OSS 后可自动上传)")
        except ImportError:
            print("\n⚠️ 无法导入 upload_report，保存到本地")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2,
                          default=serialize_datetime)
            print(f"  本地文件: {output_file}")
    else:
        # 保存到本地
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2,
                      default=serialize_datetime)
        print(f"\n已保存到本地: {output_file}")


if __name__ == "__main__":
    main()
