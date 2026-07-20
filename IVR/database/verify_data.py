"""
DB 同事脚本 2/3：验证数据正确性
- 检查工单字段完整性
- 检查对话明细一致性
- 检查槽位状态与工单对应关系
- 检查 Redis 历史与数据库对话明细一致性

用法:
    python -m database.verify_data
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import WorkOrder, DialogueDetail, AgentInfo, SessionLocal
from core import redis_manager as rm


class VerifyResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.errors: list[str] = []

    def ok(self, msg: str):
        self.passed += 1
        print(f"  [PASS] {msg}")

    def fail(self, msg: str):
        self.failed += 1
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def warn(self, msg: str):
        self.warnings += 1
        print(f"  [WARN] {msg}")

    def summary(self) -> dict:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "errors": self.errors,
            "all_passed": self.failed == 0,
        }


def verify_orders(db, result: VerifyResult):
    """验证工单表数据"""
    print("\n--- 验证工单表 ---")
    orders = db.query(WorkOrder).all()
    result.ok(f"工单总数: {len(orders)}")

    for order in orders:
        # 检查必填字段
        if not order.phone:
            result.fail(f"工单#{order.order_id} phone 为空")
        if not order.conversation_id:
            result.fail(f"工单#{order.order_id} conversation_id 为空")
        if not order.instance_id:
            result.fail(f"工单#{order.order_id} instance_id 为空")

        # 检查枚举值范围
        if order.order_type not in (0, 1, 2, 3):
            result.fail(f"工单#{order.order_id} order_type={order.order_type} 超出范围(0-3)")
        if order.order_status not in (0, 1, 2, 3):
            result.fail(f"工单#{order.order_id} order_status={order.order_status} 超出范围(0-3)")
        if order.ai_solved not in (0, 1):
            result.fail(f"工单#{order.order_id} ai_solved={order.ai_solved} 超出范围(0-1)")

        # 检查时间逻辑
        if order.call_end_time and order.call_start_time:
            if order.call_end_time < order.call_start_time:
                result.fail(f"工单#{order.order_id} call_end_time 早于 call_start_time")

        # 检查已办结工单是否有摘要
        if order.order_status == 2 and not order.biz_summary:
            result.warn(f"工单#{order.order_id} 已办结但无 biz_summary")

    result.ok("工单表字段验证完成")


def verify_dialogues(db, result: VerifyResult):
    """验证对话明细表"""
    print("\n--- 验证对话明细表 ---")
    dialogues = db.query(DialogueDetail).all()
    result.ok(f"对话明细总数: {len(dialogues)}")

    valid_roles = {"AI", "user", "worker", "ivr"}
    for dia in dialogues:
        if dia.role not in valid_roles:
            result.fail(f"对话#{dia.dia_id} role={dia.role!r} 不在有效范围{valid_roles}")
        if not dia.content:
            result.fail(f"对话#{dia.dia_id} content 为空")
        # 检查关联工单是否存在
        order = db.query(WorkOrder).filter(WorkOrder.order_id == dia.order_id).first()
        if not order:
            result.fail(f"对话#{dia.dia_id} 关联的工单#{dia.order_id} 不存在")

    result.ok("对话明细表验证完成")


def verify_slots(db, result: VerifyResult):
    """验证槽位状态与工单对应关系"""
    print("\n--- 验证槽位状态 ---")
    slots = rm.get_all_slots()
    result.ok(f"槽位总数: {len(slots)}")

    for slot in slots:
        slot_id = slot["slot_id"]
        status = slot.get("status", "idle")
        order_id = slot.get("order_id")

        if status == "busy":
            if not order_id:
                result.fail(f"Slot#{slot_id} 状态为 busy 但无 order_id")
            else:
                order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
                if not order:
                    result.fail(f"Slot#{slot_id} 占用的工单#{order_id} 不存在")
                elif order.order_status == 2:
                    result.fail(f"Slot#{slot_id} 占用的工单#{order_id} 已办结但槽位未释放")
                else:
                    result.ok(f"Slot#{slot_id} busy → 工单#{order_id} (正常)")
        else:
            if order_id:
                result.warn(f"Slot#{slot_id} 状态为 idle 但仍有 order_id={order_id}")

    result.ok("槽位状态验证完成")


def verify_redis_consistency(db, result: VerifyResult):
    """验证 Redis 历史对话与数据库对话明细一致性"""
    print("\n--- 验证 Redis 与 DB 一致性 ---")
    orders = db.query(WorkOrder).all()

    for order in orders:
        oid = order.order_id
        redis_history = rm.get_history(oid)
        db_dialogues = db.query(DialogueDetail).filter(
            DialogueDetail.order_id == oid
        ).all()

        # Redis 历史可能因滑动窗口截断，只检查 DB 有但 Redis 完全没有的情况
        if db_dialogues and not redis_history:
            result.warn(f"工单#{oid} 数据库有 {len(db_dialogues)} 条对话但 Redis 历史为空")
        elif not db_dialogues and redis_history:
            result.warn(f"工单#{oid} Redis 有 {len(redis_history)} 条历史但数据库无对话明细")

    result.ok("Redis 与 DB 一致性验证完成")


def verify_agents(db, result: VerifyResult):
    """验证坐席表"""
    print("\n--- 验证坐席表 ---")
    agents = db.query(AgentInfo).all()
    result.ok(f"坐席总数: {len(agents)}")

    for agent in agents:
        if agent.agent_status not in (0, 1, 2):
            result.fail(f"坐席#{agent.agent_id} agent_status={agent.agent_status} 超出范围(0-2)")
        if not agent.agent_name:
            result.fail(f"坐席#{agent.agent_id} agent_name 为空")

    result.ok("坐席表验证完成")


def main():
    print("=" * 60)
    print("数据验证开始")
    print("=" * 60)

    result = VerifyResult()
    db = SessionLocal()
    try:
        verify_orders(db, result)
        verify_dialogues(db, result)
        verify_agents(db, result)
        verify_slots(db, result)
        verify_redis_consistency(db, result)
    finally:
        db.close()

    print("\n" + "=" * 60)
    summary = result.summary()
    print(f"验证结果: 通过 {summary['passed']} / 失败 {summary['failed']} / "
          f"警告 {summary['warnings']}")
    if summary["errors"]:
        print("\n失败项:")
        for e in summary["errors"]:
            print(f"  - {e}")
    print(f"\n{'✅ 全部通过' if summary['all_passed'] else '❌ 存在失败项'}")
    print("=" * 60)

    # 返回退出码供脚本调用
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
