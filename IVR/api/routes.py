"""
FastAPI 路由定义：工单、智能坐席、人工坐席、对话SSE、工单流转
对齐接口文档要求
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Body, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from config import settings
from database.models import (
    WorkOrder, DialogueDetail, AgentInfo,
    QualityInspection, KnowledgeBaseFile,
    get_db, init_db,
)
from core import redis_manager as rm
from core.aliyun_client import aliyun
from core.knowledge_base import kb
from core.llm_skill import llm_skill
from core import logger as log

router = APIRouter()


# ═══════════════════════════════════════════════════════════════
#  请求/响应 模型
# ═══════════════════════════════════════════════════════════════

class OrderCreate(BaseModel):
    """IVR阶段创建空工单"""
    phone: str = Field(..., description="来电号码")
    conversation_id: str = Field(..., description="CCC会话ID")
    instance_id: str = Field(..., description="热线机器人实例ID")
    order_type: int = Field(1, description="工单类型：0-转播 1-咨询 2-投诉 3-回访（IVR按键分流结果）")


class OrderUpdate(BaseModel):
    ent_name: Optional[str] = None
    ent_address: Optional[str] = None
    ent_cerdit: Optional[str] = None
    contact_name: Optional[str] = None
    order_type: Optional[int] = None
    order_status: Optional[int] = None
    agent_id: Optional[int] = None
    biz_summary: Optional[str] = None
    ai_failure_note: Optional[str] = None
    ai_solved: Optional[int] = None


class AgentStatusUpdate(BaseModel):
    """坐席状态更新"""
    agent_id: int
    agent_status: int = Field(..., description="0-离线 1-忙碌 2-在线")
    ccc_agent_id: Optional[str] = None
    device_id: Optional[str] = None


class RobotDialogueRequest(BaseModel):
    """智能机器人对话请求"""
    order_id: int
    utterance: str = Field(..., description="用户语音转写文本")


class DispatchRequest(BaseModel):
    """工单流转推送"""
    receiver: str = "backend_processor"


# ═══════════════════════════════════════════════════════════════
#  质检模块 请求模型
# ═══════════════════════════════════════════════════════════════

class EvaluationItem(BaseModel):
    """单条评价请求"""
    inspection_id: int = Field(..., description="质检记录ID")
    evaluation: Optional[str] = Field(None, description="评价内容，传null表示清空评价")


class EvaluateRequest(BaseModel):
    """批量评价请求"""
    evaluations: List[EvaluationItem] = Field(..., description="评价列表，支持批量更新")


# ═══════════════════════════════════════════════════════════════
#  知识库模块 请求模型
# ═══════════════════════════════════════════════════════════════

class KnowledgeBaseStatusUpdate(BaseModel):
    """知识库文件状态更新请求"""
    status: int = Field(..., description="1-启用 2-停用")


# ═══════════════════════════════════════════════════════════════
#  工单接口
# ═══════════════════════════════════════════════════════════════

@router.post("/api/orders")
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    """
    IVR阶段创建空工单
    用户拨入电话、CCC创建通话后立即调用
    """
    order = WorkOrder(
        phone=payload.phone,
        conversation_id=payload.conversation_id,
        instance_id=payload.instance_id,
        order_type=payload.order_type,
        order_status=1,
        call_start_time=datetime.now(),
        created_time=datetime.now(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    log.incoming_call(payload.phone, order.order_id)
    return {"code": 200, "data": {"order_id": order.order_id}}


@router.get("/api/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    """获取工单详情（坐席弹屏用）"""
    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, "工单不存在")

    # 附带历史对话
    history = rm.get_history(order_id)
    return {
        "code": 200,
        "data": {
            "order_id": order.order_id,
            "phone": order.phone,
            "conversation_id": order.conversation_id,
            "ent_name": order.ent_name,
            "ent_address": order.ent_address,
            "ent_cerdit": order.ent_cerdit,
            "contact_name": order.contact_name,
            "order_type": order.order_type,
            "order_status": order.order_status,
            "agent_id": order.agent_id,
            "biz_summary": order.biz_summary,
            "ai_solved": order.ai_solved,
            "ai_failure_note": order.ai_failure_note,
            "call_start_time": order.call_start_time.isoformat() if order.call_start_time else None,
            "history": history,
        }
    }


@router.put("/api/orders/{order_id}")
def update_order(order_id: int, payload: OrderUpdate,
                 db: Session = Depends(get_db)):
    """更新工单（理解Skill提取后/坐席填写后）"""
    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, "工单不存在")

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(order, k, v)
    order.update_time = datetime.now()
    db.commit()
    return {"code": 200, "message": "更新成功"}


@router.get("/api/orders/by-phone/{phone}")
def get_orders_by_phone(phone: str, db: Session = Depends(get_db)):
    """
    根据电话查历史工单（完整工单信息，不含对话历史）

    用途：人工坐席接单后，前端额外调用此接口获取当前用户的历史工单列表，
    在坐席前端展示该用户的历史咨询/投诉记录（完整工单字段，便于了解用户背景）。

    注意：返回的是工单完整字段，但 **不包含** 对话历史（history）。
    如需对话详情，请单独调用 GET /api/orders/{order_id}。
    """
    orders = db.query(WorkOrder).filter(WorkOrder.phone == phone).order_by(
        WorkOrder.created_time.desc()
    ).limit(20).all()
    return {
        "code": 200,
        "data": [{
            "order_id": o.order_id,
            "phone": o.phone,
            "conversation_id": o.conversation_id,
            "instance_id": o.instance_id,
            "ent_name": o.ent_name,
            "ent_address": o.ent_address,
            "ent_cerdit": o.ent_cerdit,
            "contact_name": o.contact_name,
            "order_type": o.order_type,
            "order_status": o.order_status,
            "agent_id": o.agent_id,
            "biz_summary": o.biz_summary,
            "ai_solved": o.ai_solved,
            "ai_failure_note": o.ai_failure_note,
            "call_start_time": o.call_start_time.isoformat() if o.call_start_time else None,
            "call_end_time": o.call_end_time.isoformat() if o.call_end_time else None,
            "created_time": o.created_time.isoformat() if o.created_time else None,
            "update_time": o.update_time.isoformat() if o.update_time else None,
        } for o in orders]
    }


@router.post("/api/orders/{order_id}/dispatch")
def dispatch_order(order_id: int, payload: DispatchRequest,
                   db: Session = Depends(get_db)):
    """
    工单完结流转推送
    将工单数据推送到后端处理人员系统
    """
    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, "工单不存在")

    # 标记工单为已办结
    order.order_status = 2
    order.call_end_time = datetime.now()
    order.update_time = datetime.now()
    db.commit()

    # 构建推送数据
    history = rm.get_history(order_id)
    dispatch_data = {
        "order_id": order.order_id,
        "conversation_id": order.conversation_id,
        "phone": order.phone,
        "ent_name": order.ent_name,
        "ent_address": order.ent_address,
        "ent_cerdit": order.ent_cerdit,
        "contact_name": order.contact_name,
        "order_type": order.order_type,
        "order_status": order.order_status,
        "agent_id": order.agent_id,
        "biz_summary": order.biz_summary,
        "ai_solved": order.ai_solved,
        "ai_failure_note": order.ai_failure_note,
        "call_start_time": order.call_start_time.isoformat() if order.call_start_time else None,
        "call_end_time": order.call_end_time.isoformat() if order.call_end_time else None,
        "dialogue_summary": history,
        "dispatch_time": datetime.now().isoformat(),
        "receiver": payload.receiver,
    }

    # 实际场景: 推送到MQ / Webhook / 共享表
    # 这里仅记录日志并返回推送数据
    log.order_dispatched(order_id)
    duration = 0
    if order.call_start_time and order.call_end_time:
        duration = int((order.call_end_time - order.call_start_time).total_seconds())
    log.order_completed(order_id, duration)

    return {
        "code": 200,
        "message": "工单已推送",
        "data": {
            "dispatch_id": f"DISP-{order.order_id}",
            "dispatch_time": dispatch_data["dispatch_time"],
            "receiver": payload.receiver,
            "payload": dispatch_data,
        }
    }


# ═══════════════════════════════════════════════════════════════
#  质检模块
# ═══════════════════════════════════════════════════════════════

@router.get("/api/quality-inspection/orders")
def get_qi_orders(
    date: str = Query(..., description="日期 YYYY-MM-DD，按 call_start_time 筛选"),
    order_type: Optional[int] = Query(None, description="工单类型：0-转播 1-咨询 2-投诉 3-回访"),
    inspection_status: Optional[int] = Query(None, description="质检状态：0-待评价 1-已评价"),
    page: int = Query(1, ge=1, description="页码，默认1"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，默认20"),
    db: Session = Depends(get_db),
):
    """
    获取质检工单列表
    按日期筛选工单，并统计每个工单的对话总数、已评价数、质检状态。
    """
    # 解析日期
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "日期格式错误，应为 YYYY-MM-DD")

    # 构建基础查询：当天工单
    base_q = db.query(WorkOrder).filter(
        func.DATE(WorkOrder.call_start_time) == target_date
    )
    if order_type is not None:
        base_q = base_q.filter(WorkOrder.order_type == order_type)

    # 总数
    total = base_q.count()

    # 分页
    orders = base_q.order_by(WorkOrder.call_start_time.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()

    result_orders = []
    for o in orders:
        # 统计对话总数
        dialogue_count = db.query(func.count(DialogueDetail.dia_id)).filter(
            DialogueDetail.order_id == o.order_id
        ).scalar() or 0

        # 统计质检记录
        total_count = db.query(func.count(QualityInspection.inspection_id)).filter(
            QualityInspection.order_id == o.order_id
        ).scalar() or 0
        evaluated_count = db.query(func.count(QualityInspection.inspection_id)).filter(
            QualityInspection.order_id == o.order_id,
            QualityInspection.inspection_status == 1,
        ).scalar() or 0

        # 计算工单级质检状态：0-全部待评价 / 1-部分已评价 / 2-全部已评价
        if total_count == 0:
            qi_status = 0
        elif evaluated_count == 0:
            qi_status = 0
        elif evaluated_count < total_count:
            qi_status = 1
        else:
            qi_status = 2

        # 应用 inspection_status 筛选
        if inspection_status is not None and qi_status != inspection_status:
            continue

        result_orders.append({
            "order_id": o.order_id,
            "phone": o.phone,
            "order_type": o.order_type,
            "order_status": o.order_status,
            "ent_name": o.ent_name,
            "agent_id": o.agent_id,
            "call_start_time": o.call_start_time.isoformat() if o.call_start_time else None,
            "call_end_time": o.call_end_time.isoformat() if o.call_end_time else None,
            "dialogue_count": dialogue_count,
            "evaluated_count": evaluated_count,
            "inspection_status": qi_status,
        })

    return {
        "code": 200,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "orders": result_orders,
        }
    }


@router.get("/api/quality-inspection/orders/{order_id}/dialogues")
def get_qi_dialogues(order_id: int, db: Session = Depends(get_db)):
    """
    获取工单对话记录（含评价）
    首次访问时，系统自动从 dialogue_detail 表拉取该工单所有对话，
    将 content、role、msg_time 组装为 JSON 写入 quality_inspection 表（evaluation 为空），
    然后返回。后续访问直接返回已有质检记录。
    """
    # 查工单
    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, f"工单不存在：order_id={order_id}")

    # 检查是否已有质检记录
    existing_count = db.query(func.count(QualityInspection.inspection_id)).filter(
        QualityInspection.order_id == order_id
    ).scalar() or 0

    if existing_count == 0:
        # 首次访问：从 dialogue_detail 拉取所有对话，批量创建质检记录
        dialogues = db.query(DialogueDetail).filter(
            DialogueDetail.order_id == order_id
        ).order_by(DialogueDetail.msg_time.asc()).all()

        if dialogues:
            qi_records = []
            for d in dialogues:
                content_json = {
                    "content": d.content,
                    "role": d.role,
                    "msg_time": d.msg_time.isoformat() if d.msg_time else None,
                }
                qi = QualityInspection(
                    order_id=order_id,
                    dia_id=d.dia_id,
                    content=content_json,
                    evaluation=None,
                    inspection_status=0,
                )
                qi_records.append(qi)
            db.add_all(qi_records)
            db.commit()

    # 查询质检记录
    qi_records = db.query(QualityInspection).filter(
        QualityInspection.order_id == order_id
    ).order_by(QualityInspection.inspection_id.asc()).all()

    dialogues_data = []
    for qi in qi_records:
        dialogues_data.append({
            "inspection_id": qi.inspection_id,
            "dia_id": qi.dia_id,
            "content": qi.content,
            "evaluation": qi.evaluation,
            "inspection_status": qi.inspection_status,
        })

    return {
        "code": 200,
        "data": {
            "order_id": order.order_id,
            "phone": order.phone,
            "ent_name": order.ent_name,
            "order_type": order.order_type,
            "dialogues": dialogues_data,
        }
    }


@router.post("/api/quality-inspection/orders/{order_id}/evaluate")
def evaluate_qi(order_id: int, payload: EvaluateRequest, db: Session = Depends(get_db)):
    """
    提交/更新质检评价（批量）
    """
    if not payload.evaluations:
        raise HTTPException(400, "evaluations 不能为空")

    # 校验工单存在
    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, f"工单不存在：order_id={order_id}")

    updated_count = 0
    for item in payload.evaluations:
        qi = db.query(QualityInspection).filter(
            QualityInspection.inspection_id == item.inspection_id
        ).first()
        if not qi:
            raise HTTPException(400, f"质检记录不存在：inspection_id={item.inspection_id}")

        if qi.order_id != order_id:
            raise HTTPException(
                400,
                f"质检记录 inspection_id={item.inspection_id} 不属于工单 order_id={order_id}"
            )

        qi.evaluation = item.evaluation
        qi.inspection_status = 1 if item.evaluation else 0
        updated_count += 1

    db.commit()

    # 统计
    total_count = db.query(func.count(QualityInspection.inspection_id)).filter(
        QualityInspection.order_id == order_id
    ).scalar() or 0
    evaluated_count = db.query(func.count(QualityInspection.inspection_id)).filter(
        QualityInspection.order_id == order_id,
        QualityInspection.inspection_status == 1,
    ).scalar() or 0

    return {
        "code": 200,
        "message": "评价保存成功",
        "data": {
            "order_id": order_id,
            "evaluated_count": evaluated_count,
            "total_count": total_count,
        }
    }


@router.get("/api/quality-inspection/results")
def get_qi_results(
    date_from: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    order_id: Optional[int] = Query(None, description="指定工单ID"),
    inspection_status: Optional[int] = Query(None, description="0-待评价 1-已评价"),
    page: int = Query(1, ge=1, description="页码，默认1"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，默认20"),
    db: Session = Depends(get_db),
):
    """
    查询质检结果（多条件筛选）
    """
    # 构建查询：JOIN work_order 获取通话时间
    q = db.query(QualityInspection, WorkOrder).join(
        WorkOrder, QualityInspection.order_id == WorkOrder.order_id
    )

    # 日期范围筛选
    if date_from:
        try:
            d_from = datetime.strptime(date_from, "%Y-%m-%d").date()
            q = q.filter(func.DATE(WorkOrder.call_start_time) >= d_from)
        except ValueError:
            raise HTTPException(400, "date_from 格式错误，应为 YYYY-MM-DD")

    if date_to:
        try:
            d_to = datetime.strptime(date_to, "%Y-%m-%d").date()
            q = q.filter(func.DATE(WorkOrder.call_start_time) <= d_to)
        except ValueError:
            raise HTTPException(400, "date_to 格式错误，应为 YYYY-MM-DD")

    if order_id is not None:
        q = q.filter(QualityInspection.order_id == order_id)

    if inspection_status is not None:
        q = q.filter(QualityInspection.inspection_status == inspection_status)

    # 总数
    total = q.count()

    # 分页
    rows = q.order_by(QualityInspection.inspection_id.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()

    results = []
    for qi, wo in rows:
        results.append({
            "inspection_id": qi.inspection_id,
            "order_id": qi.order_id,
            "dia_id": qi.dia_id,
            "content": qi.content,
            "evaluation": qi.evaluation,
            "inspection_status": qi.inspection_status,
        })

    return {
        "code": 200,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "results": results,
        }
    }


# ═══════════════════════════════════════════════════════════════
#  智能坐席槽位管理
# ═══════════════════════════════════════════════════════════════

@router.get("/api/robot-slots/status")
def get_robot_slots_status():
    """
    获取所有智能坐席槽位状态
    合并 robot_agent_db 持久化数据 + Redis 实时槽位数据
    返回接口文档要求的完整格式
    """
    robot_agents = rm.query_robot_agents_detail()
    total_max = len(robot_agents)
    total_busy = sum(1 for a in robot_agents if a.get("slot_status") == "busy")

    return {
        "code": 200,
        "data": {
            "total_max_concurrency": total_max,
            "total_current_usage": total_busy,
            "queue_length": rm.get_queue_length(),
            "robot_agents": robot_agents,
        }
    }


class SystemStatusUpdate(BaseModel):
    """智能坐席系统状态更新请求"""
    system_status: str = Field(..., description="online / offline / maintenance")
    reason: str = Field("", description="操作原因")
    operator_id: str = Field("", description="操作人ID")


@router.put("/api/robot-slots/{slot_id}/system-status")
def update_robot_system_status(slot_id: int, payload: SystemStatusUpdate):
    """
    手动干预智能坐席的系统级状态
    例如：发现机器人通道死锁、响应超时，或需要话术升级重启时，
    将其置为 maintenance，系统将停止向该坐席分配新的通话槽位。
    """
    if payload.system_status not in ("online", "offline", "maintenance"):
        raise HTTPException(400, "system_status 必须为 online/offline/maintenance")

    result = rm.update_robot_agent_system_status(
        slot_id, payload.system_status,
        reason=payload.reason, operator_id=payload.operator_id,
    )

    if not result.get("success"):
        raise HTTPException(404, result.get("message", "更新失败"))

    log.info(f"[系统状态] 槽位{slot_id} {result['previous_status']} → {result['current_status']}"
             f" (操作人: {payload.operator_id}, 原因: {payload.reason})")

    return {
        "code": 200,
        "message": "智能坐席状态已更新",
        "data": {
            "slot_id": slot_id,
            "previous_status": result["previous_status"],
            "current_status": result["current_status"],
        }
    }


class HeartbeatReport(BaseModel):
    """智能坐席心跳上报请求"""
    health_status: str = Field(..., description="healthy / error / unknown")
    current_load: Optional[float] = Field(None, description="当前负载率 0-1")
    avg_response_time_ms: Optional[int] = Field(None, description="平均响应时间(ms)")


@router.post("/api/robot-slots/{slot_id}/heartbeat")
def robot_slot_heartbeat(slot_id: int, payload: HeartbeatReport):
    """
    智能坐席心跳上报
    后端定时任务或机器人服务进程定期调用此接口，更新 last_heartbeat 和 health_status。
    如果超过设定时间（如30秒）未收到心跳，系统自动将其 health_status 标记为 error，并触发告警。
    """
    if payload.health_status not in ("healthy", "error", "unknown"):
        raise HTTPException(400, "health_status 必须为 healthy/error/unknown")

    result = rm.update_robot_agent_heartbeat(
        slot_id, payload.health_status,
        current_load=payload.current_load,
        avg_response_time_ms=payload.avg_response_time_ms,
    )

    if not result.get("success"):
        raise HTTPException(404, result.get("message", "心跳上报失败"))

    return {
        "code": 200,
        "message": "心跳已更新",
        "data": {
            "slot_id": slot_id,
            "agent_name": result.get("agent_name"),
            "health_status": payload.health_status,
            "current_load": payload.current_load,
            "avg_response_time_ms": payload.avg_response_time_ms,
            "timestamp": datetime.now().isoformat(),
        }
    }


@router.post("/api/robot-slots/assign")
def assign_robot_slot(order_id: int, phone: str, db: Session = Depends(get_db)):
    """
    分配智能坐席槽位给工单
    1. 尝试找空闲槽位
    2. 无空闲则加入排队队列
    3. 分配后开启 Beebot 智能对话机器人会话
    """
    slot_id = rm.get_idle_slot()
    if not slot_id:
        position = rm.enqueue_robot(order_id, phone)
        log.slot_queued(order_id, position)
        return {"code": 200, "data": {"assigned": False, "queue_position": position}}

    # 开启 Beebot 会话
    vendor_params = {"order_id": order_id, "phone": phone, "history": []}
    try:
        session_data = aliyun.begin_session(vendor_params)
        session_id = session_data.get("SessionId", "")
        answer = session_data.get("Answer", "")
    except Exception as e:
        log.error(f"Beebot begin_session 失败: {e}")
        # 降级：即使阿里云调用失败也占用槽位
        session_id = f"local-{order_id}-{int(time.time())}"
        answer = "您好，欢迎使用大东区市场监督管理局智能服务，请问有什么可以帮您？"

    rm.occupy_slot(slot_id, order_id, session_id)
    rm.append_history(order_id, "AI", answer)
    _save_dialogue(db, order_id, answer, "AI")
    log.slot_assigned(slot_id, order_id)
    log.bot_speak(answer)

    return {
        "code": 200,
        "data": {
            "assigned": True,
            "slot_id": slot_id,
            "session_id": session_id,
            "welcome": answer,
        }
    }


@router.post("/api/robot-slots/{slot_id}/release")
def release_robot_slot(slot_id: int, db: Session = Depends(get_db)):
    """释放智能坐席槽位，并自动从队列取下一个用户"""
    rm.release_slot(slot_id)
    log.slot_released(slot_id)

    # 尝试从队列取出下一个
    next_user = rm.dequeue_robot()
    if next_user:
        # 自动分配
        order_id = next_user["order_id"]
        phone = next_user["phone"]
        try:
            session_data = aliyun.begin_session(
                {"order_id": order_id, "phone": phone, "history": []}
            )
            session_id = session_data.get("SessionId", "")
            answer = session_data.get("Answer", "")
        except Exception as e:
            log.error(f"Beebot begin_session 失败: {e}")
            session_id = f"local-{order_id}-{int(time.time())}"
            answer = "您好，请问有什么可以帮您？"

        rm.occupy_slot(slot_id, order_id, session_id)
        rm.append_history(order_id, "AI", answer)
        _save_dialogue(db, order_id, answer, "AI")
        log.slot_assigned(slot_id, order_id)
        log.bot_speak(answer)
        return {"code": 200, "data": {"released": True, "next_assigned": True,
                                      "next_order_id": order_id}}

    return {"code": 200, "data": {"released": True, "next_assigned": False}}


# ═══════════════════════════════════════════════════════════════
#  智能机器人对话
# ═══════════════════════════════════════════════════════════════

@router.post("/api/robot/dialogue")
def robot_dialogue(payload: RobotDialogueRequest, db: Session = Depends(get_db)):
    """
    智能机器人对话（Beebot 智能对话机器人）
    1. 记录用户输入
    2. 检查"拒绝解答"
    3. 调用 Beebot SSE 流式对话（携带历史对话JSON）
    4. 检查是否触发转人工（sysToAgent指令）
    5. 理解Skill提取信息
    """
    order_id = payload.order_id
    utterance = payload.utterance

    # 记录用户输入
    rm.append_history(order_id, "user", utterance)
    _save_dialogue(db, order_id, utterance, "user")
    log.user_speak(utterance)

    # 1. 拒绝解答检测
    rejected = kb.is_rejected(utterance)
    if rejected:
        log.reject_hit(rejected["question"])
        _trigger_transfer(order_id, "拒绝解答: " + rejected["question"], db)
        return {"code": 200, "data": {
            "action": "transfer_to_agent",
            "reason": "拒绝解答",
            "reject_item": rejected,
        }}

    # 2. 获取会话信息 + 历史对话
    slot_id = rm.find_slot_by_order(order_id)
    slot_info = rm.get_slot_status(slot_id) if slot_id else {}
    session_id = slot_info.get("session_id", "")
    history = rm.get_history(order_id)

    # 3. 调用 Beebot 对话（VendorParam 携带历史对话JSON）
    vendor_params = {
        "order_id": order_id,
        "phone": slot_info.get("current_phone", ""),
        "history": history,
    }
    try:
        result = aliyun.dialogue(session_id, utterance, vendor_params)
        answer = result.get("Answer", "")
        commands = result.get("Commands", [])
    except Exception as e:
        log.error(f"Beebot dialogue 失败: {e}")
        answer = "抱歉，系统暂时无法响应，正在为您转接人工客服。"
        commands = [{"Type": "Transfer"}]

    # 4. 记录机器人回答
    rm.append_history(order_id, "AI", answer)
    _save_dialogue(db, order_id, answer, "AI")
    log.bot_speak(answer)

    # 5. 检查转人工指令（sysToAgent）
    transfer_triggered = any(p.get("Type") == "Transfer" for p in commands)
    if transfer_triggered:
        reason = commands[0].get("Reason", "机器人转人工") if commands else "机器人转人工"
        _trigger_transfer(order_id, f"机器人转人工: {reason}", db)
        return {"code": 200, "data": {"action": "transfer_to_agent",
                                      "answer": answer, "reason": reason}}

    # 6. 理解Skill提取信息（biz_summary 改由人工坐席办结时生成，这里不更新）
    follow_up = None
    try:
        extracted = llm_skill.understand(history)
        log.skill_extract(json.dumps(extracted, ensure_ascii=False))
        # 更新工单（biz_summary 除外，biz_summary 由人工办结时生成）
        order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
        if order:
            if extracted.get("ent_name"):
                order.ent_name = extracted["ent_name"]
            if extracted.get("ent_address"):
                order.ent_address = extracted["ent_address"]
            if extracted.get("ent_cerdit"):
                order.ent_cerdit = extracted["ent_cerdit"]
            if extracted.get("contact_name"):
                order.contact_name = extracted["contact_name"]
            if extracted.get("phone"):
                order.phone = extracted["phone"]
            if extracted.get("order_type") is not None:
                order.order_type = extracted["order_type"]
            order.update_time = datetime.now()
            db.commit()

        # 7. 填写Skill: 若有缺失字段，生成追问话术
        missing = extracted.get("missing_fields", [])
        if missing:
            fill_result = llm_skill.fill(extracted, history)
            if fill_result.get("action") == "ask":
                follow_up = fill_result.get("question", "")
                if follow_up:
                    rm.append_history(order_id, "AI", follow_up)
                    _save_dialogue(db, order_id, follow_up, "AI")
                    log.bot_speak(follow_up)
    except Exception as e:
        log.error(f"理解Skill失败: {e}")

    return {"code": 200, "data": {
        "action": "answer", "answer": answer, "follow_up": follow_up}}


# ═══════════════════════════════════════════════════════════════
#  人工坐席管理
# ═══════════════════════════════════════════════════════════════

@router.put("/api/agent/status")
def update_agent_status(payload: AgentStatusUpdate, db: Session = Depends(get_db)):
    """
    更新坐席状态
    同时调用CCC SignInGroup/SignOutGroup同步真实状态
    """
    agent = db.query(AgentInfo).filter(AgentInfo.agent_id == payload.agent_id).first()
    if not agent:
        raise HTTPException(404, "坐席不存在")

    # 更新本地
    agent.agent_status = payload.agent_status
    if payload.ccc_agent_id:
        agent.ccc_agent_id = payload.ccc_agent_id
    db.commit()

    # 更新Redis缓存
    status_map = {0: "offline", 1: "busy", 2: "idle"}
    rm.set_agent_status(payload.agent_id, status_map[payload.agent_status])

    # 同步CCC
    if payload.ccc_agent_id:
        try:
            if payload.agent_status == 2 and payload.device_id:
                # 上线: 签入技能组 + 就绪
                aliyun.sign_in_group(
                    payload.ccc_agent_id, payload.device_id
                )
                aliyun.ready_for_service(payload.ccc_agent_id)
            elif payload.agent_status == 0:
                # 下线: 签出
                aliyun.sign_out_group(payload.ccc_agent_id)
            elif payload.agent_status == 1:
                # 忙碌: 小休
                aliyun.take_break(payload.ccc_agent_id)
        except Exception as e:
            log.error(f"CCC状态同步失败: {e}")

    return {"code": 200, "message": "坐席状态已更新"}


@router.get("/api/agents")
def list_agents(db: Session = Depends(get_db)):
    """获取所有坐席列表及状态"""
    agents = db.query(AgentInfo).all()
    return {
        "code": 200,
        "data": [{
            "agent_id": a.agent_id,
            "agent_name": a.agent_name,
            "agent_status": a.agent_status,
            "ccc_agent_id": a.ccc_agent_id,
            "redis_status": rm.get_agent_status(a.agent_id),
        } for a in agents]
    }


@router.get("/api/agents/status")
def get_all_agents_status():
    """获取所有坐席实时状态（用于前端大盘）"""
    return {
        "code": 200,
        "data": {
            "idle_count": len(list(rm.r.scan_iter("agent:*:status"))),
        }
    }


# ═══════════════════════════════════════════════════════════════
#  人工坐席队列管理
# ═══════════════════════════════════════════════════════════════

@router.get("/api/agent/queue")
def get_agent_queue():
    """查看人工坐席排队队列"""
    items = rm.get_agent_queue_items()
    return {
        "code": 200,
        "data": {
            "queue_length": len(items),
            "items": items,
        }
    }


@router.post("/api/agent/accept")
def agent_accept_order(payload: dict = Body(...), db: Session = Depends(get_db)):
    """
    人工坐席接单（从队列取工单）
    1. 从人工队列取出下一个工单
    2. 设置 call_start_time（人工开始处理时间）
    3. 绑定 agent_id
    4. 更新坐席状态为 busy
    """
    agent_id = payload.get("agent_id")
    if not agent_id:
        raise HTTPException(400, "缺少 agent_id")

    agent = db.query(AgentInfo).filter(AgentInfo.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(404, "坐席不存在")

    # 优先从队列取
    queue_item = rm.dequeue_agent()
    if queue_item:
        order_id = queue_item["order_id"]
    else:
        # 队列为空，允许指定 order_id 直接接单（兜底）
        order_id = payload.get("order_id")
        if not order_id:
            raise HTTPException(404, "队列为空且未指定 order_id")

    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, f"工单 #{order_id} 不存在")

    # 更新工单
    order.agent_id = agent_id
    order.call_start_time = datetime.now()
    order.order_status = 1  # 处理中
    order.update_time = datetime.now()
    db.commit()

    # 更新坐席状态
    agent.agent_status = 1

    rm.set_agent_status(agent_id, "busy")
    db.commit()

    log.agent_answer(agent.agent_name, order_id)
    log.info(f"[人工接单] 坐席 {agent.agent_name} 接手工单#{order_id}")

    return {
        "code": 200,
        "message": "接单成功",
        "data": {
            "order_id": order.order_id,
            "phone": order.phone,
            "conversation_id": order.conversation_id,
            "instance_id": order.instance_id,
            "ent_name": order.ent_name,
            "ent_address": order.ent_address,
            "ent_cerdit": order.ent_cerdit,
            "contact_name": order.contact_name,
            "order_type": order.order_type,
            "order_status": order.order_status,
            "agent_id": order.agent_id,
            "biz_summary": order.biz_summary,
            "ai_solved": order.ai_solved,
            "ai_failure_note": order.ai_failure_note,
            "call_start_time": order.call_start_time.isoformat() if order.call_start_time else None,
            "call_end_time": order.call_end_time.isoformat() if order.call_end_time else None,
            "created_time": order.created_time.isoformat() if order.created_time else None,
            "update_time": order.update_time.isoformat() if order.update_time else None,
        }
    }


@router.post("/api/agent/dialogue")
def agent_dialogue(payload: dict = Body(...), db: Session = Depends(get_db)):
    """
    人工坐席对话（坐席与用户之间的交互）
    保存到 dialogue_detail 表，role = "worker" 或 "user"
    同时追加到 Redis 历史对话，供后续 LLM 摘要使用
    """
    order_id = payload.get("order_id")
    agent_id = payload.get("agent_id")
    message = payload.get("message", "")
    role = payload.get("role", "user")  # worker=坐席发言, user=用户发言

    if not order_id or not message:
        raise HTTPException(400, "缺少 order_id 或 message")

    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, f"工单 #{order_id} 不存在")

    # 保存到 PostgreSQL
    dialogue = DialogueDetail(
        order_id=order_id,
        content=message,
        role=role,
    )
    db.add(dialogue)
    db.commit()

    # 追加到 Redis 历史对话（供 LLM 摘要使用）
    rm.append_history(order_id, role, message)

    log.info(f"[人工对话] 工单#{order_id} [{role}] {message[:80]}")

    return {
        "code": 200,
        "message": "对话已保存",
        "data": {
            "order_id": order_id,
            "role": role,
            "content": message,
        }
    }


@router.post("/api/agent/complete")
def agent_complete_order(payload: dict = Body(...), db: Session = Depends(get_db)):
    """
    人工坐席办结工单
    1. LLM 生成 biz_summary（人工处理总结）
    2. 设置 call_end_time（人工处理结束时间）
    3. 工单状态置为已办结
    4. 释放坐席状态为 idle
    5. 从人工队列自动取下一个工单（如果有）
    """
    order_id = payload.get("order_id")
    agent_id = payload.get("agent_id")
    manual_summary = payload.get("manual_summary", "")  # 允许人工直接填写

    if not order_id:
        raise HTTPException(400, "缺少 order_id")

    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if not order:
        raise HTTPException(404, f"工单 #{order_id} 不存在")

    # 生成 biz_summary
    if manual_summary:
        biz_summary = manual_summary
    else:
        # LLM 辅助生成（基于 AI对话 + 人工对话历史）
        history = rm.get_history(order_id)
        try:
            biz_summary = llm_skill.summarize(history, role="human")
            log.info(f"[人工摘要] 工单#{order_id}: {biz_summary[:80]}")
        except Exception as e:
            log.error(f"LLM 人工摘要生成失败: {e}")
            biz_summary = "人工处理摘要生成失败，请人工填写"
        # 兜底：LLM 返回空时使用默认值
        if not biz_summary or not biz_summary.strip():
            biz_summary = f"人工坐席#{agent_id} 已处理工单#{order_id}"

    # 更新工单
    order.biz_summary = biz_summary
    order.call_end_time = datetime.now()
    order.order_status = 2  # 已办结
    order.ai_solved = 0  # 转人工的工单 ai_solved = 0
    order.update_time = datetime.now()
    db.commit()

    # 释放坐席状态
    if agent_id:
        agent = db.query(AgentInfo).filter(AgentInfo.agent_id == agent_id).first()
        if agent:
            agent.agent_status = 2
        
            rm.set_agent_status(agent_id, "idle")
            db.commit()
            log.info(f"[人工办结] 坐席 {agent.agent_name} 释放")

    log.order_completed(order_id, 0)
    log.order_dispatched(order_id)

    # 从人工队列自动取下一个工单（如果有）
    next_order = rm.dequeue_agent()
    next_info = None
    if next_order and agent_id:
        next_id = next_order["order_id"]
        no = db.query(WorkOrder).filter(WorkOrder.order_id == next_id).first()
        if no:
            no.agent_id = agent_id
            no.call_start_time = datetime.now()
            no.order_status = 1
            no.update_time = datetime.now()
            db.commit()
            # 坐席保持 busy
            rm.set_agent_status(agent_id, "busy")
            db.query(AgentInfo).filter(AgentInfo.agent_id == agent_id).update(
                {"agent_status": 1})
            db.commit()
            log.info(f"[自动接单] 坐席接手下一个工单#{next_id}")
            next_info = {
                "next_order_id": next_id,
                "ai_failure_note": no.ai_failure_note,
                "phone": no.phone,
            }

    return {
        "code": 200,
        "message": "工单已办结",
        "data": {
            "order_id": order_id,
            "biz_summary": biz_summary,
            "call_end_time": order.call_end_time.isoformat() if order.call_end_time else None,
            "next_order": next_info,
        }
    }


@router.get("/api/agent/queue/status")
def get_agent_queue_status():
    """查看人工坐席队列详细状态"""
    return {
        "code": 200,
        "data": {
            "queue_length": rm.get_agent_queue_length(),
            "queue_items": rm.get_agent_queue_items(),
        }
    }


# ═══════════════════════════════════════════════════════════════
#  知识库模块
# ═══════════════════════════════════════════════════════════════

@router.post("/api/knowledge-base/upload")
async def upload_knowledge_base_file(
    file: UploadFile = File(..., description="上传的文件"),
    description: str = Form("", description="文件描述"),
    db: Session = Depends(get_db),
):
    """
    上传知识库文件
    支持 .xlsx, .xls, .pdf, .txt, .docx, .csv，最大 50MB
    """
    if not file.filename:
        raise HTTPException(400, "请选择要上传的文件")

    # 校验文件扩展名
    allowed_exts = settings.KB_ALLOWED_EXTENSIONS.split(",")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(
            400,
            f"不支持的文件类型：{ext}，允许的类型：{settings.KB_ALLOWED_EXTENSIONS}"
        )

    # 读取文件内容
    content_bytes = await file.read()
    file_size = len(content_bytes)

    # 校验文件大小
    if file_size > settings.KB_MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        max_mb = settings.KB_MAX_FILE_SIZE / (1024 * 1024)
        raise HTTPException(400, f"文件大小 {size_mb:.0f}MB 超出限制，最大允许 {max_mb:.0f}MB")

    # 确保上传目录存在
    os.makedirs(settings.KB_UPLOAD_DIR, exist_ok=True)

    # 生成唯一文件名：YYYYMMDD_HHmmss_uuid8_原始文件名
    now = datetime.now()
    unique_name = f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}_{file.filename}"
    file_path = os.path.join(settings.KB_UPLOAD_DIR, unique_name)

    # 写入文件
    with open(file_path, "wb") as f:
        f.write(content_bytes)

    # 写入数据库
    kb_file = KnowledgeBaseFile(
        file_name=file.filename,
        file_path=file_path,
        file_type=ext.lstrip("."),
        file_size=file_size,
        status=1,
        upload_time=now,
        description=description,
    )
    db.add(kb_file)
    db.commit()
    db.refresh(kb_file)

    return {
        "code": 200,
        "message": "上传成功",
        "data": {
            "file_id": kb_file.file_id,
            "file_name": kb_file.file_name,
            "file_path": kb_file.file_path,
            "file_type": kb_file.file_type,
            "file_size": kb_file.file_size,
            "status": kb_file.status,
            "upload_time": kb_file.upload_time.isoformat() if kb_file.upload_time else None,
            "description": kb_file.description,
        }
    }


@router.get("/api/knowledge-base/files")
def get_knowledge_base_files(
    status: Optional[int] = Query(None, description="筛选状态：0-处理中 1-已启用 2-已停用"),
    page: int = Query(1, ge=1, description="页码，默认1"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数，默认20"),
    db: Session = Depends(get_db),
):
    """
    获取知识库文件列表
    """
    q = db.query(KnowledgeBaseFile)
    if status is not None:
        q = q.filter(KnowledgeBaseFile.status == status)

    total = q.count()
    files = q.order_by(KnowledgeBaseFile.upload_time.desc()) \
        .offset((page - 1) * page_size).limit(page_size).all()

    return {
        "code": 200,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "files": [{
                "file_id": f.file_id,
                "file_name": f.file_name,
                "file_path": f.file_path,
                "file_type": f.file_type,
                "file_size": f.file_size,
                "status": f.status,
                "upload_time": f.upload_time.isoformat() if f.upload_time else None,
                "description": f.description,
            } for f in files],
        }
    }


@router.delete("/api/knowledge-base/files/{file_id}")
def delete_knowledge_base_file(file_id: int, db: Session = Depends(get_db)):
    """
    删除知识库文件（数据库记录 + 物理文件）
    """
    kb_file = db.query(KnowledgeBaseFile).filter(
        KnowledgeBaseFile.file_id == file_id
    ).first()
    if not kb_file:
        raise HTTPException(404, f"知识库文件不存在：file_id={file_id}")

    # 删除物理文件（不阻断流程）
    try:
        if os.path.exists(kb_file.file_path):
            os.remove(kb_file.file_path)
    except Exception as e:
        log.error(f"删除物理文件失败: {e}")

    # 删除数据库记录
    db.delete(kb_file)
    db.commit()

    return {"code": 200, "message": "删除成功"}


@router.put("/api/knowledge-base/files/{file_id}/status")
def update_knowledge_base_file_status(
    file_id: int,
    payload: KnowledgeBaseStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    更新知识库文件状态（启用/停用）
    """
    if payload.status not in (1, 2):
        raise HTTPException(400, f"无效的状态值：{payload.status}，允许的值：1-启用 2-停用")

    kb_file = db.query(KnowledgeBaseFile).filter(
        KnowledgeBaseFile.file_id == file_id
    ).first()
    if not kb_file:
        raise HTTPException(404, f"知识库文件不存在：file_id={file_id}")

    kb_file.status = payload.status
    db.commit()

    return {
        "code": 200,
        "message": "状态更新成功",
        "data": {
            "file_id": kb_file.file_id,
            "file_name": kb_file.file_name,
            "status": kb_file.status,
        }
    }


# ═══════════════════════════════════════════════════════════════
#  对话 SSE 流式推送
# ═══════════════════════════════════════════════════════════════

@router.get("/api/dialogue/stream/{order_id}")
async def dialogue_stream(order_id: int, db: Session = Depends(get_db)):
    """
    SSE流式推送对话转写文本到坐席前端
    坐席接听后建立连接，实时接收对话内容
    """
    async def event_generator():
        last_dia_id = 0
        while True:
            # 查询新增的对话记录
            new_dialogues = db.query(DialogueDetail).filter(
                DialogueDetail.order_id == order_id,
                DialogueDetail.dia_id > last_dia_id
            ).order_by(DialogueDetail.dia_id).all()

            for d in new_dialogues:
                last_dia_id = d.dia_id
                data = {
                    "dia_id": d.dia_id,
                    "role": d.role,
                    "content": d.content,
                    "msg_time": d.msg_time.isoformat() if d.msg_time else None,
                }
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

            await asyncio.sleep(2)  # 每2秒轮询一次

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _save_dialogue(db: Session, order_id: int, content: str, role: str):
    """保存对话到数据库"""
    dialogue = DialogueDetail(
        order_id=order_id,
        content=content,
        role=role,
        msg_time=datetime.now(),
    )
    db.add(dialogue)
    db.commit()


def _trigger_transfer(order_id: int, reason: str, db: Session):
    """
    触发转人工兜底
    1. 释放智能坐席槽位
    2. LLM 生成 AI 对话摘要 (ai_failure_note)
    3. 入人工坐席排队队列
    4. 查找空闲人工坐席，有空闲则直接分配并调用CCC转接
    5. 更新工单
    """
    log.transfer_to_agent(reason)

    # 释放智能坐席槽位
    slot_id = rm.find_slot_by_order(order_id)
    if slot_id:
        # 获取 session_id 用于结束 Beebot
        slot_info = rm.get_slot_status(slot_id)
        session_id = slot_info.get("session_id", "")
        rm.release_slot(slot_id)
        log.slot_released(slot_id)
        # 结束 Beebot 会话
        if session_id:
            try:
                aliyun.end_session(session_id)
            except Exception as e:
                log.error(f"Beebot end_session 失败: {e}")
        # 从智能坐席队列取下一个
        next_user = rm.dequeue_robot()
        if next_user:
            try:
                sd = aliyun.begin_session(
                    {"order_id": next_user["order_id"],
                     "phone": next_user["phone"],
                     "history": []}
                )
                rm.occupy_slot(slot_id, next_user["order_id"],
                               sd.get("SessionId", ""))
                rm.append_history(next_user["order_id"], "AI",
                                  sd.get("Answer", ""))
                log.slot_assigned(slot_id, next_user["order_id"])
            except Exception as e:
                log.error(f"智能坐席队列用户分配失败: {e}")

    # 生成 AI 对话摘要
    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if order:
        history = rm.get_history(order_id)
        ai_summary = ""
        if history:
            # 有对话历史，用 LLM 生成摘要
            try:
                ai_summary = llm_skill.summarize(history, role="ai")
                log.info(f"[AI摘要] 工单#{order_id}: {ai_summary[:80]}")
            except Exception as e:
                log.error(f"AI 摘要生成失败: {e}")
                ai_summary = reason
        else:
            # 无对话历史（如按键0直接转人工），直接用转人工原因
            ai_summary = reason
            log.info(f"[AI摘要] 工单#{order_id}: {ai_summary}（无对话历史）")

        order.ai_solved = 0
        order.ai_failure_note = ai_summary
        order.update_time = datetime.now()
        db.commit()

        # 入人工坐席排队队列
        position = rm.enqueue_agent(order_id, order.phone, ai_summary)
        log.info(f"[人工队列] 工单#{order_id} 入队，位置#{position}")

    # 查找空闲人工坐席
    agent_id = rm.get_idle_agent()
    if agent_id:
        agent = db.query(AgentInfo).filter(AgentInfo.agent_id == agent_id).first()
        if agent:
            rm.set_agent_status(agent_id, "busy")
            agent.agent_status = 1
        
            if order:
                order.agent_id = agent_id
                order.call_start_time = datetime.now()
            db.commit()
            log.agent_answer(agent.agent_name, order_id)

            # 调用 CCC 盲转，将通话转接给人工坐席
            try:
                aliyun.blind_transfer(
                    transferee=agent.ccc_agent_id,
                    user_id=agent.ccc_agent_id,
                )
                log.info(f"CCC 盲转成功 → {agent.ccc_agent_id}")
            except Exception as e:
                log.error(f"CCC 盲转失败: {e}")

            return {"transferred": True, "agent_id": agent_id,
                    "agent_name": agent.agent_name}

    log.info("无空闲人工坐席，进入人工队列等待")
    return {"transferred": False, "message": "进入人工坐席队列等待"}


# ═══════════════════════════════════════════════════════════════
#  CCC 事件回调
# ═══════════════════════════════════════════════════════════════

@router.post("/api/ccc/callback")
async def ccc_callback(
    db: Session = Depends(get_db),
    payload: dict = Body(
        ...,
        examples={
            "Released": {
                "summary": "用户挂断",
                "value": {
                    "eventType": "Released",
                    "contactId": "job-test-001",
                    "releaseInitiator": "User",
                    "instanceId": "demo-1334882287961657",
                },
            },
            "Established": {
                "summary": "通话建立",
                "value": {
                    "eventType": "Established",
                    "contactId": "job-test-001",
                    "agentId": "agent001@demo-1334882287961657",
                    "instanceId": "demo-1334882287961657",
                },
            },
            "AssignAgentFailure": {
                "summary": "分配坐席失败",
                "value": {
                    "eventType": "AssignAgentFailure",
                    "contactId": "job-test-001",
                    "reason": "坐席忙",
                    "instanceId": "demo-1334882287961657",
                },
            },
            "RecordingReady": {
                "summary": "录音就绪",
                "value": {
                    "eventType": "RecordingReady",
                    "ContactId": "job-test-001",
                    "FileUrl": "http://example.com/rec.wav",
                    "instanceId": "demo-1334882287961657",
                },
            },
            "AgentReady": {
                "summary": "坐席就绪",
                "value": {
                    "eventType": "AgentReady",
                    "agentId": "agent001@demo-1334882287961657",
                    "instanceId": "demo-1334882287961657",
                },
            },
            "TextStream": {
                "summary": "实时文本流",
                "value": {
                    "eventType": "TextStream",
                    "contactId": "job-test-001",
                    "channelType": "caller",
                    "text": "我想咨询营业执照办理流程",
                    "instanceId": "demo-1334882287961657",
                },
            },
            "IvrKeyPressed": {
                "summary": "IVR按键（自定义测试事件）",
                "value": {
                    "EventType": "IvrKeyPressed",
                    "ConversationId": "conv-test-001",
                    "Key": "1",
                    "InstanceId": "demo-1334882287961657",
                },
            },
        },
    ),
):
    """
    CCC 事件回调入口（手动测试用）

    注意：阿里云 CCC 事件推送仅支持通过 RocketMQ 5.0，不支持 HTTP Webhook。
    生产环境通过 RocketMQ 消费者（core/rocketmq_consumer.py）处理事件。
    此接口保留用于本地手动测试和模拟事件触发。
    """
    event_type = payload.get("eventType") or payload.get("EventType", "")
    log.info(f"[HTTP回调] CCC 事件: type={event_type}")

    # 幂等去重
    dedup_key = payload.get("EventId", "") or f"http-{event_type}-{time.time()}"
    if not rm.set_event_processed(dedup_key):
        log.info(f"[HTTP回调] 重复事件已跳过")
        return {"code": 200, "message": "duplicated"}

    # 分发处理
    try:
        handler = _CCC_EVENT_HANDLERS.get(event_type)
        if handler:
            handler(payload, db)
        else:
            log.info(f"[HTTP回调] 未识别的 CCC 事件类型: {event_type}")
    except Exception as e:
        log.error(f"[HTTP回调] 处理失败 type={event_type}: {e}")

    return {"code": 200, "message": "ok"}


# ── CCC 事件处理函数 ─────────────────────────────────────────────

def _find_order_by_conversation(db: Session, conversation_id: str):
    """通过 CCC 会话 ID 反查工单"""
    if not conversation_id:
        return None
    return db.query(WorkOrder).filter(
        WorkOrder.conversation_id == conversation_id
    ).order_by(WorkOrder.order_id.desc()).first()


def _extract_conversation_id(payload: dict) -> str:
    """从回调 payload 中提取会话ID
    兼容官方 CCC 2.0 字段名（contactId）和旧版自定义字段名"""
    return (payload.get("contactId")           # 官方 CCC 2.0 话务事件字段名
            or payload.get("ContactId")        # 官方 RecordingReady 等非话务事件字段名
            or payload.get("ConversationId")   # 旧版自定义字段名（兼容）
            or payload.get("conversationId")
            or "")


def _create_order_internal(db: Session, phone: str, conversation_id: str,
                           instance_id: str, order_type: int = 1):
    """内部创建工单逻辑（供 API 和事件处理器共用）"""
    order = WorkOrder(
        phone=phone,
        conversation_id=conversation_id,
        instance_id=instance_id,
        order_type=order_type,
        order_status=1,
        created_time=datetime.now(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _assign_robot_slot_internal(db: Session, order_id: int, phone: str) -> dict:
    """
    内部分配智能坐席槽位逻辑（供 API 和事件处理器共用）
    返回: {"assigned": bool, ...}
    """
    slot_id = rm.get_idle_slot()
    if not slot_id:
        position = rm.enqueue_robot(order_id, phone)
        log.slot_queued(order_id, position)
        return {"assigned": False, "queue_position": position}

    vendor_params = {"order_id": order_id, "phone": phone, "history": []}
    try:
        session_data = aliyun.begin_session(vendor_params)
        session_id = session_data.get("SessionId", "")
        answer = session_data.get("Answer", "")
    except Exception as e:
        log.error(f"Beebot begin_session 失败: {e}")
        session_id = f"local-{order_id}-{int(time.time())}"
        answer = "您好，欢迎使用大东区市场监督管理局智能服务，请问有什么可以帮您？"

    rm.occupy_slot(slot_id, order_id, session_id)
    rm.append_history(order_id, "AI", answer)
    _save_dialogue(db, order_id, answer, "AI")
    log.slot_assigned(slot_id, order_id)
    log.bot_speak(answer)
    return {"assigned": True, "slot_id": slot_id,
            "session_id": session_id, "welcome": answer}


def _handle_call_started(payload: dict, db: Session):
    """
    振铃事件（Ringing）— 来电接入
    仅缓存来电信息，等待后续 Established 事件创建工单并启动 Beebot。
    按键1/2 → 企业咨询/投诉 → 分配智能坐席 + 启动 Beebot
    按键0   → 直接转人工
    """
    conv_id = _extract_conversation_id(payload)
    phone = (payload.get("caller") or payload.get("Caller")  # 官方字段名: caller
             or payload.get("From") or "")
    instance_id = (payload.get("instanceId") or payload.get("InstanceId")
                   or settings.CCC_INSTANCE_ID)
    log.info(f"[CCC事件] Ringing conv={conv_id} phone={phone}")

    if not conv_id:
        log.error("Ringing 缺少 contactId，无法缓存来电")
        return

    # 缓存来电信息，等待 Established 事件创建工单
    rm.cache_pending_call(conv_id, phone or "unknown", instance_id)
    log.ivr_pending(phone or "unknown")


def _handle_call_answered(payload: dict, db: Session):
    """通话建立事件（Established）— 坐席（人工/机器人）接听"""
    conv_id = _extract_conversation_id(payload)
    agent_id = payload.get("agentId") or payload.get("UserId") or payload.get("AgentId", "")
    log.info(f"[CCC事件] Established conv={conv_id} agent={agent_id}")

    order = _find_order_by_conversation(db, conv_id)
    if not order:
        log.info(f"Established 未找到工单 conv={conv_id}")
        return

    # 关联坐席到工单
    if agent_id:
        agent = db.query(AgentInfo).filter(
            AgentInfo.ccc_agent_id == agent_id
        ).first()
        if agent:
            order.agent_id = agent.agent_id
            agent.agent_status = 1  # busy
        
            rm.set_agent_status(agent.agent_id, "busy")
            log.agent_answer(agent.agent_name, order.order_id)
    order.update_time = datetime.now()
    db.commit()


def _handle_call_hangup(payload: dict, db: Session):
    """
    挂机事件（Released）— 最关键事件
    1. 释放智能坐席槽位（如果在AI阶段挂断）
    2. 结束 Beebot 会话
    3. AI 解决判定: 槽位曾被占用且未触发转人工 → ai_solved=1
    4. AI 解决时: call_start_time 保持为通话开始时间，不重置
    5. 转人工的工单不在本事件处理 call_end_time（由人工办结接口设置）
    6. 队列取下一个用户
    """
    conv_id = _extract_conversation_id(payload)
    release_initiator = (payload.get("releaseInitiator")  # 官方字段名
                         or payload.get("HangupDir", ""))
    log.info(f"[CCC事件] Released conv={conv_id} initiator={release_initiator}")

    order = _find_order_by_conversation(db, conv_id)
    if not order:
        log.info(f"Released 未找到工单 conv={conv_id}")
        return

    order_id = order.order_id

    # 1. 释放智能坐席槽位（如果还在 AI 阶段）
    slot_id = rm.find_slot_by_order(order_id)
    if slot_id:
        # 获取 session_id 用于结束 Beebot
        slot_info = rm.get_slot_status(slot_id)
        session_id = slot_info.get("session_id", "")
        rm.release_slot(slot_id)
        log.slot_released(slot_id)
        # 结束 Beebot 会话
        if session_id:
            try:
                aliyun.end_session(session_id)
            except Exception as e:
                log.error(f"Beebot end_session 失败: {e}")

    # 2. AI 解决判定: 槽位曾被占用且未触发转人工 → 视为 AI 解决
    #    转人工的工单 ai_failure_note 已被设置（_cleanup_robot_transfer），不会判定为 AI 解决
    #    额外兜底：如果工单已关联人工坐席（agent_id 不为空），也视为非 AI 解决
    ai_solved = 0
    if slot_id and not order.ai_failure_note and not order.agent_id:
        ai_solved = 1

    order.ai_solved = ai_solved

    # 3. 时间字段处理
    if ai_solved:
        # AI 解决: call_start_time 保持为通话开始时间，不重置
        # call_start_time 保持为通话开始时间，不重置
        order.call_end_time = None
        order.order_status = 2  # 已办结
        # 生成 AI 对话摘要（作为工单总结）
        history = rm.get_history(order_id)
        if history:
            try:
                ai_summary = llm_skill.summarize(history, role="ai")
                if ai_summary and ai_summary.strip():
                    order.ai_failure_note = ai_summary
                    log.info(f"[AI摘要] 工单#{order_id}: {ai_summary[:80]}")
                else:
                    order.ai_failure_note = "AI 对话已结束"
            except Exception as e:
                log.error(f"AI 摘要生成失败: {e}")
                order.ai_failure_note = "AI 对话已结束"
        else:
            order.ai_failure_note = "AI 对话已结束"
    else:
        # 转人工: 如果有 agent_id 说明已被人工坐席接听，按挂断处理
        # 如果没有 agent_id 说明还在排队，不设置 call_end_time
        if order.agent_id:
            order.call_end_time = datetime.now()
            order.order_status = 2
        else:
            # 仍在排队中挂断 → 主动挂断
            order.order_status = 0

    order.update_time = datetime.now()
    db.commit()

    # 通话时长日志（仅人工处理完时有意义）
    duration = 0
    if order.call_start_time and order.call_end_time:
        duration = int(
            (order.call_end_time - order.call_start_time).total_seconds()
        )
    log.order_completed(order_id, duration)

    # 4. 队列取下一个用户自动分配（智能坐席队列）
    if slot_id:
        next_user = rm.dequeue_robot()
        if next_user:
            try:
                sd = aliyun.begin_session({
                    "order_id": next_user["order_id"],
                    "phone": next_user["phone"],
                    "history": [],
                })
                rm.occupy_slot(slot_id, next_user["order_id"],
                               sd.get("SessionId", ""))
                rm.append_history(next_user["order_id"], "AI",
                                  sd.get("Answer", ""))
                log.slot_assigned(slot_id, next_user["order_id"])
            except Exception as e:
                log.error(f"队列用户分配失败: {e}")


def _handle_transfer_completed(payload: dict, db: Session):
    """
    转接成功（自定义事件，保留用于测试）
    官方 CCC 转接通过 Established 事件的 scenario 字段（BLIND_TRANSFER/ATTENDED_TRANSFER）体现
    """
    conv_id = _extract_conversation_id(payload)
    agent_id = payload.get("agentId") or payload.get("UserId") or payload.get("TargetAgentId", "")
    log.info(f"[CCC事件] TransferCompleted conv={conv_id} agent={agent_id}")

    order = _find_order_by_conversation(db, conv_id)
    if not order:
        return

    # 关联坐席
    if agent_id:
        agent = db.query(AgentInfo).filter(
            AgentInfo.ccc_agent_id == agent_id
        ).first()
        if agent:
            order.agent_id = agent.agent_id
            agent.agent_status = 1
        
            rm.set_agent_status(agent.agent_id, "busy")
    order.update_time = datetime.now()
    db.commit()


def _handle_transfer_failed(payload: dict, db: Session):
    """
    分配坐席失败（AssignAgentFailure）
    官方字段: reason（失败原因）
    """
    conv_id = _extract_conversation_id(payload)
    reason = payload.get("reason") or payload.get("Reason", "未知原因")
    log.error(f"[CCC事件] AssignAgentFailure conv={conv_id} reason={reason}")

    order = _find_order_by_conversation(db, conv_id)
    if not order:
        return

    # 追加失败原因，触发重转
    order.ai_failure_note = f"转接失败: {reason}"
    order.update_time = datetime.now()
    db.commit()

    # 触发重新转人工
    _trigger_transfer(order.order_id, f"转接失败重试: {reason}", db)


def _handle_recording_ready(payload: dict, db: Session):
    """
    录音就绪（RecordingReady）— 按需求仅打印日志不入库
    （未新增 recording_url 字段）
    """
    conv_id = _extract_conversation_id(payload)
    file_url = payload.get("FileUrl") or payload.get("RecordingUrl", "")
    log.info(f"[CCC事件] RecordingReady conv={conv_id} url={file_url}")


# ── 坐席状态映射（官方事件类型 → 本地状态） ──
_AGENT_STATUS_MAP = {
    "AgentCheckIn":  ("ready",    2),   # 签入 → 在线空闲
    "AgentReady":    ("idle",     2),   # 就绪 → 在线空闲
    "AgentDialing":  ("busy",     1),   # 拨号 → 忙碌
    "AgentRinging":  ("busy",     1),   # 振铃 → 忙碌
    "AgentTalk":     ("busy",     1),   # 通话 → 忙碌
    "AgentRelease":  ("idle",     2),   # 挂机 → 在线空闲
    "AgentBreak":    ("busy",     1),   # 小休 → 忙碌
    "AgentCheckOut": ("offline",  0),   # 签出 → 离线
    "AgentRingingTimeout": ("idle", 2), # 振铃超时 → 在线空闲
}


def _handle_agent_status_change(payload: dict, db: Session):
    """
    坐席状态变化（官方 CCC 坐席事件）
    支持 9 个官方坐席事件类型：AgentCheckIn/AgentReady/AgentDialing/AgentRinging/
    AgentTalk/AgentRelease/AgentBreak/AgentCheckOut/AgentRingingTimeout
    官方字段: agentId（坐席ID），eventType（事件类型）
    """
    agent_id = payload.get("agentId") or payload.get("UserId", "")
    event_type = payload.get("eventType") or payload.get("EventType", "")
    log.info(f"[CCC事件] {event_type} agent={agent_id}")

    if not agent_id:
        return

    agent = db.query(AgentInfo).filter(
        AgentInfo.ccc_agent_id == agent_id
    ).first()
    if not agent:
        return

    # 根据官方事件类型映射到本地状态
    status_info = _AGENT_STATUS_MAP.get(event_type, ("busy", 1))
    redis_status, db_status = status_info

    agent.agent_status = db_status
    rm.set_agent_status(agent.agent_id, redis_status)
    db.commit()


def _handle_asr_sentence_result(payload: dict, db: Session):
    """
    实时文本流（TextStream）— 语音转写结果
    CCC 实时语音转文字推送，将转写文本写入对话记录。
    人工坐席可通过 SSE 流实时查看对话内容。
    官方字段: text（转写文本），channelType（通道类型，如 caller/agent）
    """
    conv_id = _extract_conversation_id(payload)
    text = payload.get("text") or payload.get("Text") or payload.get("Transcript") or ""
    channel_type = (payload.get("channelType") or payload.get("Role")
                    or payload.get("Speaker") or "")
    log.info(f"[CCC事件] TextStream conv={conv_id} channel={channel_type} text={text[:50]}")

    if not text:
        return

    order = _find_order_by_conversation(db, conv_id)
    if not order:
        log.info(f"TextStream 未找到工单 conv={conv_id}")
        return

    # 角色映射: caller/customer → user, agent/worker → worker
    channel_lower = str(channel_type).lower()
    if "agent" in channel_lower or "worker" in channel_lower or "seat" in channel_lower:
        dia_role = "worker"
    else:
        dia_role = "user"

    # 保存转写文本到对话记录（供 SSE 流推送给坐席前端）
    _save_dialogue(db, order.order_id, text, dia_role)
    rm.append_history(order.order_id, dia_role, text)
    if dia_role == "user":
        log.user_speak(text)
    else:
        log.info(f"[人工坐席] {text}")


def _handle_ivr_key_pressed(payload: dict, db: Session):
    """
    IVR 按键事件（自定义事件，保留用于测试）
    ⚠️ 注意：官方 CCC 没有 IvrKeyPressed 事件！
    生产环境通过 CCC IVR 联系流配置实现按键分流，触发 Enqueue → AssignAgent 事件。
    本函数仅用于本地 HTTP 回调模拟测试。
    
    按键1 → 企业咨询 → 创建工单 + 分配智能坐席 + 启动 Beebot 对话
    按键2 → 投诉办理 → 创建工单 + 分配智能坐席 + 启动 Beebot 对话
    按键0 → 转人工   → 创建工单 + 直接转人工坐席（不经过 Beebot）
    """
    conv_id = _extract_conversation_id(payload)
    key = payload.get("Key") or payload.get("key") or payload.get("Dtmf") or ""
    log.info(f"[CCC事件] IvrKeyPressed conv={conv_id} key={key}")

    # 取出 Ringing 阶段缓存的来电信息
    pending = rm.get_pending_call(conv_id)
    if not pending:
        log.error(f"IvrKeyPressed 未找到来电缓存 conv={conv_id}，可能已超时")
        return

    phone = pending.get("phone", "unknown")
    instance_id = pending.get("instance_id", settings.CCC_INSTANCE_ID)

    # 幂等：检查工单是否已存在
    existing = _find_order_by_conversation(db, conv_id)
    if existing:
        log.info(f"工单已存在 #{existing.order_id}，跳过创建")
        rm.clear_pending_call(conv_id)
        return

    # 按键分流
    if key == "1":
        # 企业咨询 → Beebot 智能对话
        order = _create_order_internal(db, phone, conv_id, instance_id, order_type=1)
        log.incoming_call(phone, order.order_id)
        log.ivr_route(phone, "", key, "咨询")
        _assign_robot_slot_internal(db, order.order_id, phone)
        rm.clear_pending_call(conv_id)

    elif key == "2":
        # 投诉办理 → Beebot 智能对话
        order = _create_order_internal(db, phone, conv_id, instance_id, order_type=2)
        log.incoming_call(phone, order.order_id)
        log.ivr_route(phone, "", key, "投诉")
        _assign_robot_slot_internal(db, order.order_id, phone)
        rm.clear_pending_call(conv_id)

    elif key == "0":
        # 转人工 → 不经过 Beebot，直接转人工坐席
        order = _create_order_internal(db, phone, conv_id, instance_id, order_type=1)
        log.incoming_call(phone, order.order_id)
        log.ivr_transfer_direct()
        _trigger_transfer(order.order_id, "IVR直接转人工", db)
        rm.clear_pending_call(conv_id)

    else:
        log.info(f"未识别的 IVR 按键: {key}，忽略")


def _handle_dtmf_result(payload: dict, db: Session):
    """
    DTMF 按键结果（自定义事件，保留用于测试）
    ⚠️ 注意：官方 CCC 没有 DtmfResult 事件！
    生产环境 DTMF 按键通过 CCC IVR 联系流处理。
    本函数仅用于本地 HTTP 回调模拟测试。
    
    用户在智能机器人对话时按下电话按键 0 → 触发转人工
    """
    conv_id = _extract_conversation_id(payload)
    dtmf = payload.get("Dtmf") or payload.get("dtmf") or ""
    log.info(f"[CCC事件] DtmfResult conv={conv_id} dtmf={dtmf}")

    # 根据 conversation_id 查找工单
    order = _find_order_by_conversation(db, conv_id)
    if not order:
        log.error(f"DtmfResult 未找到对应工单 conv={conv_id}，忽略")
        return

    if dtmf == "0":
        # 用户按键 0 → 触发转人工
        log.info(f"[DTMF按键转人工] 工单#{order.order_id} 由用户按键0触发")
        _trigger_transfer(order.order_id, "对话过程中按键转人工", db)
    else:
        log.info(f"未处理的 DTMF 按键: {dtmf}，忽略")


# ── 新增官方事件处理器 ──

def _handle_abandoned(payload: dict, db: Session):
    """
    IVR中放弃（Abandoned）— 客户在IVR交互过程中主动挂机
    官方字段: abandonPhase（放弃阶段：IVR/Queuing/Ringing）
    """
    conv_id = _extract_conversation_id(payload)
    abandon_phase = payload.get("abandonPhase", "unknown")
    log.info(f"[CCC事件] Abandoned conv={conv_id} phase={abandon_phase}")

    # 清理该通话的缓存
    pending = rm.get_pending_call(conv_id)
    if pending:
        rm.clear_pending_call(conv_id)
        log.info(f"Abandoned 清理来电缓存 conv={conv_id}")


def _is_robot_agent(agent_id: str) -> bool:
    """判断 agentId 是否属于智能机器人坐席
    规则：等于配置的机器人坐席前缀，或 agentId 含 "robot"
    """
    if not agent_id:
        return False
    if settings.CCC_ROBOT_AGENT_PREFIX and agent_id.startswith(settings.CCC_ROBOT_AGENT_PREFIX):
        return True
    return "robot" in agent_id.lower()


def _parse_call_variables(payload: dict) -> dict:
    """解析 CCC 事件中的 callVariables 字段
    IVR 联系流中设置的自定义变量通过此字段传递
    返回 dict，如 {"order_type": "1"} 或 {}"""
    raw = payload.get("callVariables", "")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if isinstance(raw, str) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _handle_enqueue(payload: dict, db: Session):
    """
    IVR转人工（Enqueue）— 客户进入IVR转人工队列
    官方字段: skillGroupId（技能组ID）, callVariables（IVR自定义变量）
    
    生产环境：
    - IVR 联系流中按键1→设置 callVariables.order_type=1，按键2→order_type=2
    - 按键0→不设置 order_type 或设为0，标识转人工
    - 进入队列时创建工单，根据 callVariables.order_type 区分咨询/投诉
    """
    conv_id = _extract_conversation_id(payload)
    skill_group_id = payload.get("skillGroupId", "")
    call_vars = _parse_call_variables(payload)
    order_type = int(call_vars.get("order_type", 1) or 1)
    log.info(f"[CCC事件] Enqueue conv={conv_id} skillGroup={skill_group_id} order_type={order_type}")

    # 取出 Ringing 阶段缓存的来电信息
    pending = rm.get_pending_call(conv_id)
    if not pending:
        log.info(f"Enqueue 未找到来电缓存 conv={conv_id}，尝试用事件字段创建")
        phone = payload.get("caller", "unknown")
        instance_id = payload.get("instanceId", settings.CCC_INSTANCE_ID)
    else:
        phone = pending.get("phone", "unknown")
        instance_id = pending.get("instance_id", settings.CCC_INSTANCE_ID)

    # 幂等：检查工单是否已存在
    existing = _find_order_by_conversation(db, conv_id)
    if existing:
        log.info(f"工单已存在 #{existing.order_id}，跳过创建")
        # 如果工单已存在且 order_type=0（按键0转人工）→ 说明用户从机器人转人工
        # 需要清理机器人资源：释放槽位、结束Beebot、生成AI摘要
        if order_type == 0:
            _cleanup_robot_transfer(db, existing.order_id)
        return

    # 创建工单
    order = _create_order_internal(db, phone, conv_id, instance_id, order_type=order_type)
    log.incoming_call(phone, order.order_id)
    log.ivr_route(phone, skill_group_id, "", "咨询" if order_type == 1 else ("投诉" if order_type == 2 else "转人工"))

    log.info(f"Enqueue 创建工单 #{order.order_id} type={order_type} 等待分配坐席")


def _cleanup_robot_transfer(db: Session, order_id: int):
    """
    清理机器人资源（用户按键0从机器人转人工时调用）
    1. 释放智能坐席槽位
    2. 结束 Beebot 会话
    3. 生成 AI 对话摘要
    4. 设置 ai_failure_note（防止 Released 事件误判为 AI 解决）
    5. 从智能坐席队列取下一个用户
    """
    slot_id = rm.find_slot_by_order(order_id)
    if not slot_id:
        log.info(f"_cleanup_robot_transfer 工单#{order_id} 无机器人槽位，跳过")
        return

    # 获取 session_id 用于结束 Beebot
    slot_info = rm.get_slot_status(slot_id)
    session_id = slot_info.get("session_id", "")
    rm.release_slot(slot_id)
    log.slot_released(slot_id)

    # 结束 Beebot 会话
    if session_id:
        try:
            aliyun.end_session(session_id)
        except Exception as e:
            log.error(f"Beebot end_session 失败: {e}")

    # 生成 AI 对话摘要
    order = db.query(WorkOrder).filter(WorkOrder.order_id == order_id).first()
    if order:
        history = rm.get_history(order_id)
        ai_summary = ""
        if history:
            try:
                ai_summary = llm_skill.summarize(history, role="ai")
                log.info(f"[AI摘要] 工单#{order_id}: {ai_summary[:80]}")
            except Exception as e:
                log.error(f"AI 摘要生成失败: {e}")
                ai_summary = "用户按键转人工"
        else:
            ai_summary = "用户按键转人工"

        order.ai_failure_note = ai_summary
        order.ai_solved = 0
        order.update_time = datetime.now()
        db.commit()
        log.info(f"_cleanup_robot_transfer 工单#{order_id} 机器人清理完成")

    # 从智能坐席队列取下一个用户
    next_user = rm.dequeue_robot()
    if next_user:
        try:
            sd = aliyun.begin_session(
                {"order_id": next_user["order_id"],
                 "phone": next_user["phone"],
                 "history": []}
            )
            new_sid = sd.get("SessionId", "")
            rm.occupy_slot(slot_id, next_user["order_id"], new_sid)
            rm.append_history(next_user["order_id"], "AI", sd.get("Answer", ""))
            log.slot_assigned(slot_id, next_user["order_id"])
        except Exception as e:
            log.error(f"智能坐席队列用户分配失败: {e}")


def _handle_assign_agent(payload: dict, db: Session):
    """
    分配坐席（AssignAgent）— 客户的通话成功分配到坐席
    官方字段: agentId（坐席ID），skillGroupId（技能组ID）
    
    单技能组方案：
    - 通过 agentId 区分机器人/人工（机器人坐席以配置的 CCC_ROBOT_AGENT_PREFIX 开头）
    - 机器人坐席 → 启动 Beebot 对话
    - 人工坐席 → 关联坐席到工单
    """
    conv_id = _extract_conversation_id(payload)
    agent_id = payload.get("agentId", "")
    skill_group_id = payload.get("skillGroupId", "")
    log.info(f"[CCC事件] AssignAgent conv={conv_id} agent={agent_id} skillGroup={skill_group_id}")

    order = _find_order_by_conversation(db, conv_id)
    if not order:
        log.info(f"AssignAgent 未找到工单 conv={conv_id}，可能尚未创建")
        return

    # 清理来电缓存
    rm.clear_pending_call(conv_id)

    # 根据 agentId 判断：智能机器人 or 人工坐席
    if _is_robot_agent(agent_id):
        # 智能机器人坐席 → 启动 Beebot 对话
        log.info(f"AssignAgent 分配智能坐席 #{order.order_id} agent={agent_id}")
        _assign_robot_slot_internal(db, order.order_id, order.phone)
    else:
        # 人工坐席 → 先清理机器人资源（兜底），再关联坐席
        _cleanup_robot_transfer(db, order.order_id)
        log.info(f"AssignAgent 分配人工坐席 #{order.order_id} agent={agent_id}")
        if agent_id:
            agent = db.query(AgentInfo).filter(
                AgentInfo.ccc_agent_id == agent_id
            ).first()
            if agent:
                order.agent_id = agent.agent_id
                agent.agent_status = 1  # busy
                rm.set_agent_status(agent.agent_id, "busy")
                log.agent_answer(agent.agent_name, order.order_id)
            else:
                log.error(f"AssignAgent 未找到本地坐席记录 ccc_agent_id={agent_id}")
        order.call_start_time = datetime.now()
        order.update_time = datetime.now()
        db.commit()


def _handle_ivr_tracking(payload: dict, db: Session):
    """
    IVR轨迹事件（IvrTracking）— 记录IVR节点流转信息
    官方字段: contactFlowId（联系流ID），contactFlowType（联系流类型）
    当前仅记录日志，后续可扩展为IVR路径分析
    """
    conv_id = _extract_conversation_id(payload)
    flow_id = payload.get("contactFlowId", "")
    flow_type = payload.get("contactFlowType", "")
    log.info(f"[CCC事件] IvrTracking conv={conv_id} flowId={flow_id} flowType={flow_type}")


# ── 事件分发映射表 ───────────────────────────────────────────────
# 所有事件名已与阿里云 CCC 2.0 官方事件名对齐
# 参考文档: https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats
_CCC_EVENT_HANDLERS = {
    # ── 话务事件（通道事件） ──
    "Ringing":           _handle_call_started,          # 振铃 → 缓存来电信息
    "Established":       _handle_call_answered,         # 通话建立 → 关联坐席
    "Released":          _handle_call_hangup,           # 挂机 → 释放槽位/办结
    # ── IVR 路由事件 ──
    "Abandoned":         _handle_abandoned,             # IVR中放弃 → 清理缓存
    "Enqueue":           _handle_enqueue,               # 进入转人工队列 → 创建工单
    "AssignAgent":       _handle_assign_agent,          # 分配坐席 → 机器人/人工分流
    "AssignAgentFailure": _handle_transfer_failed,      # 分配坐席失败 → 重试转接
    # ── 实时流事件 ──
    "TextStream":        _handle_asr_sentence_result,   # ASR实时转写
    # ── 录音事件 ──
    "RecordingReady":    _handle_recording_ready,       # 录音就绪
    # ── 坐席事件（9个官方事件类型） ──
    "AgentCheckIn":      _handle_agent_status_change,   # 坐席签入
    "AgentReady":        _handle_agent_status_change,   # 坐席就绪
    "AgentDialing":      _handle_agent_status_change,   # 坐席拨号
    "AgentRinging":      _handle_agent_status_change,   # 坐席振铃
    "AgentTalk":         _handle_agent_status_change,   # 坐席通话
    "AgentRelease":      _handle_agent_status_change,   # 坐席挂机
    "AgentBreak":        _handle_agent_status_change,   # 坐席小休
    "AgentCheckOut":     _handle_agent_status_change,   # 坐席签出
    "AgentRingingTimeout": _handle_agent_status_change, # 坐席振铃超时
    # ── IVR轨迹事件 ──
    "IvrTracking":       _handle_ivr_tracking,          # IVR节点轨迹
    # ── 自定义测试事件（仅用于本地 HTTP 回调模拟，生产环境不会触发） ──
    "IvrKeyPressed":     _handle_ivr_key_pressed,       # ⚠️ 自定义：IVR按键（测试用）
    "DtmfResult":        _handle_dtmf_result,           # ⚠️ 自定义：DTMF按键（测试用）
    "TransferCompleted": _handle_transfer_completed,    # ⚠️ 自定义：转接完成（测试用）
}
