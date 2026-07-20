r"""
质检模块 + 知识库模块 — 独立测试脚本
不需要启动服务，直接调用 FastAPI TestClient 测试全部 8 个新接口

用法：
    cd f:/360MoveData/Users/myh/Desktop/IVR
    python tests/test_quality_inspection.py
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import text
from database.models import SessionLocal, WorkOrder, DialogueDetail, AgentInfo, QualityInspection, KnowledgeBaseFile


def setup_test_data():
    """清理旧数据 + 插入测试数据，返回工单列表"""
    db = SessionLocal()

    # 清理质检和知识库数据
    db.query(QualityInspection).delete()
    db.query(KnowledgeBaseFile).delete()
    db.query(DialogueDetail).delete()
    db.query(WorkOrder).delete()
    db.commit()

    # 重置序列
    db.execute(text("ALTER SEQUENCE IF EXISTS work_order_order_id_seq RESTART WITH 1"))
    db.execute(text("ALTER SEQUENCE IF EXISTS dialogue_detail_dia_id_seq RESTART WITH 1"))
    db.execute(text("ALTER SEQUENCE IF EXISTS quality_inspection_inspection_id_seq RESTART WITH 1"))
    db.execute(text("ALTER SEQUENCE IF EXISTS knowledge_base_files_file_id_seq RESTART WITH 1"))
    db.commit()

    # 创建测试工单 1（咨询类，有完整对话）
    now = datetime.now()
    order1 = WorkOrder(
        conversation_id="test-conv-001",
        instance_id="test-instance",
        phone="13800001111",
        order_type=1,  # 咨询
        order_status=2,  # 已办结
        ent_name="某某科技有限公司",
        agent_id=1,
        call_start_time=now.replace(hour=9, minute=30, second=0),
        call_end_time=now.replace(hour=9, minute=38, second=0),
    )
    db.add(order1)
    db.flush()

    # 为工单1创建对话记录
    dialogues_1 = [
        ("您好，请问有什么可以帮您？", "AI", now.replace(hour=9, minute=30, second=5)),
        ("我想咨询一下营业执照怎么办理", "user", now.replace(hour=9, minute=30, second=15)),
        ("好的，营业执照办理需要准备以下材料：1. 公司名称预先核准通知书 2. 公司章程 3. 股东身份证明 4. 经营场所证明...", "AI", now.replace(hour=9, minute=30, second=25)),
        ("那办理需要多长时间？", "user", now.replace(hour=9, minute=31, second=0)),
        ("正在为您转接人工客服，请稍候...", "AI", now.replace(hour=9, minute=31, second=5)),
        ("您好，我是人工客服，关于营业执照办理时限，一般材料齐全的话3-5个工作日可以完成。", "worker", now.replace(hour=9, minute=31, second=30)),
    ]
    for content, role, msg_time in dialogues_1:
        db.add(DialogueDetail(order_id=order1.order_id, content=content, role=role, msg_time=msg_time))

    # 创建测试工单 2（投诉类，对话较少）
    order2 = WorkOrder(
        conversation_id="test-conv-002",
        instance_id="test-instance",
        phone="13900002222",
        order_type=2,  # 投诉
        order_status=2,
        ent_name="某某餐饮管理有限公司",
        agent_id=2,
        call_start_time=now.replace(hour=10, minute=15, second=0),
        call_end_time=now.replace(hour=10, minute=22, second=0),
    )
    db.add(order2)
    db.flush()

    dialogues_2 = [
        ("您好，这里是市场监督管理局，请问有什么可以帮您？", "worker", now.replace(hour=10, minute=15, second=5)),
        ("我要投诉XX餐厅卫生不达标！", "user", now.replace(hour=10, minute=15, second=10)),
        ("好的，请问具体是哪家餐厅？我们会记录并处理。", "worker", now.replace(hour=10, minute=15, second=20)),
        ("就是XX路XX号的XX餐厅，后厨卫生极差！", "user", now.replace(hour=10, minute=15, second=35)),
        ("已记录，我们会尽快安排执法人员上门检查，请您保持电话畅通。", "worker", now.replace(hour=10, minute=16, second=0)),
    ]
    for content, role, msg_time in dialogues_2:
        db.add(DialogueDetail(order_id=order2.order_id, content=content, role=role, msg_time=msg_time))

    db.commit()
    print(f"✓ 已创建测试数据：工单 {order1.order_id}（6条对话）、工单 {order2.order_id}（5条对话）")
    db.close()
    return order1.order_id, order2.order_id


def test_all(client, order1_id, order2_id):
    """测试全部 8 个接口"""
    passed = 0
    failed = 0
    today = datetime.now().strftime("%Y-%m-%d")

    def check(label, resp, expected_code=200):
        nonlocal passed, failed
        status = resp.status_code
        body = resp.json()
        if status == expected_code:
            passed += 1
            print(f"  [PASS] {label} → HTTP {status}")
        else:
            failed += 1
            print(f"  [FAIL] {label} → HTTP {status}, body={json.dumps(body, ensure_ascii=False)}")
        return body

    print("\n" + "=" * 60)
    print("一、质检模块测试")
    print("=" * 60)

    # 1.1 获取质检工单列表
    print("\n▶ 1.1 GET /api/quality-inspection/orders?date={}".format(today))
    resp = client.get(f"/api/quality-inspection/orders?date={today}")
    body = check("获取质检工单列表", resp)
    if body.get("code") == 200:
        orders = body["data"]["orders"]
        print(f"    → 返回 {len(orders)} 个工单")
        for o in orders:
            print(f"      工单#{o['order_id']} | {o['ent_name']} | 对话{o['dialogue_count']}条 | 已评价{o['evaluated_count']}条 | 质检状态={o['inspection_status']}")

    # 1.2 首次访问工单对话（自动创建质检记录）
    print(f"\n▶ 1.2 GET /api/quality-inspection/orders/{order1_id}/dialogues（首次访问）")
    resp = client.get(f"/api/quality-inspection/orders/{order1_id}/dialogues")
    body = check("获取工单1对话（首次）", resp)
    if body.get("code") == 200:
        dialogues = body["data"]["dialogues"]
        print(f"    → 返回 {len(dialogues)} 条对话记录")
        for d in dialogues:
            role = d["content"]["role"]
            text = d["content"]["content"][:30]
            ev = d["evaluation"] or "（空）"
            print(f"      inspection_id={d['inspection_id']} | [{role}] {text}... | 评价={ev}")

    # 1.3 再次访问（直接返回已有记录）
    print(f"\n▶ 1.3 GET /api/quality-inspection/orders/{order1_id}/dialogues（再次访问，验证幂等）")
    resp = client.get(f"/api/quality-inspection/orders/{order1_id}/dialogues")
    body = check("获取工单1对话（再次）", resp)
    if body.get("code") == 200:
        print(f"    → 返回 {len(body['data']['dialogues'])} 条（未重复创建）")

    # 1.4 提交评价
    print(f"\n▶ 1.4 POST /api/quality-inspection/orders/{order1_id}/evaluate")
    evaluate_body = {
        "evaluations": [
            {"inspection_id": 1, "evaluation": "开场白规范，符合标准话术"},
            {"inspection_id": 2, "evaluation": None},
            {"inspection_id": 3, "evaluation": "回答准确完整，但语速偏快"},
            {"inspection_id": 4, "evaluation": None},
            {"inspection_id": 5, "evaluation": "转人工时机合理"},
            {"inspection_id": 6, "evaluation": "人工客服回答专业，态度良好"},
        ]
    }
    resp = client.post(f"/api/quality-inspection/orders/{order1_id}/evaluate", json=evaluate_body)
    body = check("提交评价", resp)
    if body.get("code") == 200:
        print(f"    → 已评价 {body['data']['evaluated_count']}/{body['data']['total_count']} 条")

    # 1.5 验证评价已保存
    print(f"\n▶ 1.5 GET /api/quality-inspection/orders/{order1_id}/dialogues（验证评价已保存）")
    resp = client.get(f"/api/quality-inspection/orders/{order1_id}/dialogues")
    body = check("验证评价", resp)
    if body.get("code") == 200:
        for d in body["data"]["dialogues"]:
            if d["evaluation"]:
                print(f"      inspection_id={d['inspection_id']} | 评价={d['evaluation']} | status={d['inspection_status']}")

    # 1.6 查询质检结果
    print(f"\n▶ 1.6 GET /api/quality-inspection/results?inspection_status=1")
    resp = client.get("/api/quality-inspection/results?inspection_status=1")
    body = check("查询已评价记录", resp)
    if body.get("code") == 200:
        print(f"    → 已评价 {body['data']['total']} 条记录")

    # 1.7 工单2也获取对话（触发自动创建）
    print(f"\n▶ 1.7 GET /api/quality-inspection/orders/{order2_id}/dialogues")
    resp = client.get(f"/api/quality-inspection/orders/{order2_id}/dialogues")
    body = check("获取工单2对话", resp)
    if body.get("code") == 200:
        print(f"    → 返回 {len(body['data']['dialogues'])} 条（自动创建成功）")

    # 1.8 工单2提交评价
    print(f"\n▶ 1.8 POST /api/quality-inspection/orders/{order2_id}/evaluate")
    evaluate_body2 = {
        "evaluations": [
            {"inspection_id": 7, "evaluation": "人工接听及时"},
            {"inspection_id": 8, "evaluation": None},
            {"inspection_id": 9, "evaluation": "记录详细，态度良好"},
            {"inspection_id": 10, "evaluation": None},
            {"inspection_id": 11, "evaluation": "处理方案明确"},
        ]
    }
    resp = client.post(f"/api/quality-inspection/orders/{order2_id}/evaluate", json=evaluate_body2)
    body = check("工单2提交评价", resp)
    if body.get("code") == 200:
        print(f"    → 已评价 {body['data']['evaluated_count']}/{body['data']['total_count']} 条")

    # 1.9 按日期范围查询全部质检结果
    print(f"\n▶ 1.9 GET /api/quality-inspection/results?date_from={today}&date_to={today}")
    resp = client.get(f"/api/quality-inspection/results?date_from={today}&date_to={today}")
    body = check("按日期范围查询", resp)
    if body.get("code") == 200:
        print(f"    → 共 {body['data']['total']} 条质检记录")

    print("\n" + "=" * 60)
    print("二、知识库模块测试")
    print("=" * 60)

    # 2.1 上传 Excel 文件
    print("\n▶ 2.1 POST /api/knowledge-base/upload")
    test_content = "分组名\t问题\t相似问法\t答案\n营业执照\t如何办理营业执照？\t怎么办执照\t请携带身份证到工商局办理\n"
    files = {"file": ("测试知识库.xlsx", test_content.encode("utf-8"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    data = {"description": "测试用知识库文件"}
    resp = client.post("/api/knowledge-base/upload", files=files, data=data)
    body = check("上传xlsx", resp)
    if body.get("code") == 200:
        print(f"    → file_id={body['data']['file_id']}, file_name={body['data']['file_name']}")

    # 2.2 上传 txt 文件
    print("\n▶ 2.2 POST /api/knowledge-base/upload（txt文件）")
    txt_content = "投诉处理规范：1. 耐心倾听 2. 记录详情 3. 告知处理流程 4. 跟进反馈".encode("utf-8")
    files = {"file": ("投诉处理规范.txt", txt_content, "text/plain")}
    data = {"description": "投诉处理标准话术"}
    resp = client.post("/api/knowledge-base/upload", files=files, data=data)
    body = check("上传txt", resp)
    if body.get("code") == 200:
        print(f"    → file_id={body['data']['file_id']}, file_name={body['data']['file_name']}")

    # 2.3 上传 pdf 文件
    print("\n▶ 2.3 POST /api/knowledge-base/upload（pdf文件）")
    pdf_content = b"%PDF-1.4 test pdf content"
    files = {"file": ("食品经营许可指南.pdf", pdf_content, "application/pdf")}
    data = {"description": "食品经营许可证办理指南"}
    resp = client.post("/api/knowledge-base/upload", files=files, data=data)
    body = check("上传pdf", resp)
    if body.get("code") == 200:
        print(f"    → file_id={body['data']['file_id']}, file_name={body['data']['file_name']}")

    # 2.4 获取文件列表
    print("\n▶ 2.4 GET /api/knowledge-base/files")
    resp = client.get("/api/knowledge-base/files")
    body = check("获取文件列表", resp)
    if body.get("code") == 200:
        print(f"    → 共 {body['data']['total']} 个文件")
        for f in body["data"]["files"]:
            print(f"      file_id={f['file_id']} | {f['file_name']} | {f['file_type']} | {f['file_size']}B | status={f['status']}")

    # 2.5 停用文件
    print("\n▶ 2.5 PUT /api/knowledge-base/files/1/status（停用）")
    resp = client.put("/api/knowledge-base/files/1/status", json={"status": 2})
    body = check("停用文件", resp)
    if body.get("code") == 200:
        print(f"    → {body['data']['file_name']} 状态变为 {body['data']['status']}")

    # 2.6 重新启用
    print("\n▶ 2.6 PUT /api/knowledge-base/files/1/status（启用）")
    resp = client.put("/api/knowledge-base/files/1/status", json={"status": 1})
    body = check("启用文件", resp)
    if body.get("code") == 200:
        print(f"    → {body['data']['file_name']} 状态变为 {body['data']['status']}")

    # 2.7 按状态筛选
    print("\n▶ 2.7 GET /api/knowledge-base/files?status=2")
    resp = client.get("/api/knowledge-base/files?status=2")
    body = check("按状态筛选", resp)
    if body.get("code") == 200:
        print(f"    → 已停用文件 {body['data']['total']} 个")

    # 2.8 删除文件
    print("\n▶ 2.8 DELETE /api/knowledge-base/files/3")
    resp = client.delete("/api/knowledge-base/files/3")
    body = check("删除文件", resp)
    if body.get("code") == 200:
        print(f"    → 删除成功")

    # 2.9 验证删除后的列表
    print("\n▶ 2.9 GET /api/knowledge-base/files（验证删除后）")
    resp = client.get("/api/knowledge-base/files")
    body = check("删除后列表", resp)
    if body.get("code") == 200:
        print(f"    → 剩余 {body['data']['total']} 个文件")

    # 2.10 错误场景测试
    print("\n▶ 2.10 错误场景测试")
    resp = client.post("/api/knowledge-base/upload", files={"file": ("test.jpg", b"fake", "image/jpeg")})
    body = check("非法文件类型", resp, expected_code=400)
    if body.get("code") == 400:
        print(f"    → {body['message']}")

    resp = client.put("/api/knowledge-base/files/1/status", json={"status": 3})
    body = check("无效状态值", resp, expected_code=400)
    if body.get("code") == 400:
        print(f"    → {body['message']}")

    resp = client.delete("/api/knowledge-base/files/999")
    body = check("删除不存在的文件", resp, expected_code=404)
    if body.get("code") == 404:
        print(f"    → {body['message']}")

    # 总结
    print("\n" + "=" * 60)
    print(f"测试结果：通过 {passed} 个，失败 {failed} 个")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    from main import app

    print("=" * 60)
    print("质检模块 + 知识库模块 测试脚本")
    print("=" * 60)

    with TestClient(app) as client:
        order1_id, order2_id = setup_test_data()
        success = test_all(client, order1_id, order2_id)

    if success:
        print("\n🎉 全部测试通过！")
    else:
        print("\n❌ 存在失败用例，请检查")
    sys.exit(0 if success else 1)