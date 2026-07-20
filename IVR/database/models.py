"""
PostgreSQL 数据库模型
对齐需求文档中的三张表：主工单表、对话明细表、坐席表
"""
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, BigInteger, String, Text, Integer,
    SmallInteger, DateTime, ForeignKey, Index, UniqueConstraint, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

from config import settings

Base = declarative_base()


class WorkOrder(Base):
    """主工单表"""
    __tablename__ = "work_order"

    order_id = Column(BigInteger, primary_key=True, autoincrement=True,
                      comment="工单唯一主键")
    conversation_id = Column(String(64), nullable=False,
                             comment="会话ID，由CCC平台生成")
    instance_id = Column(String(64), nullable=False,
                         comment="热线机器人实例ID")
    ent_name = Column(String(100), nullable=True, comment="企业名称")
    ent_address = Column(String(500), nullable=True, comment="企业经营地址")
    ent_cerdit = Column(String(18), nullable=True,
                        comment="统一社会信用代码")
    phone = Column(String(20), nullable=False, comment="来电号码")
    contact_name = Column(String(100), nullable=True, comment="联系人姓名")
    order_type = Column(SmallInteger, nullable=False, default=1,
                        comment="工单类型：0-转播 1-咨询 2-投诉 3-回访")
    order_status = Column(SmallInteger, nullable=False, default=1,
                          comment="工单状态：0-主动挂断 1-处理中 2-已办结 3-待回访 4-排队中 5-振铃中")
    agent_id = Column(BigInteger, nullable=True, comment="受理坐席ID")
    created_time = Column(DateTime, nullable=False, default=datetime.now,
                          comment="工单创建时间")
    update_time = Column(DateTime, nullable=True, comment="最后更新时间")
    call_start_time = Column(DateTime, nullable=False, default=datetime.now,
                             comment="通话开始时间")
    call_end_time = Column(DateTime, nullable=True, comment="通话结束时间")
    biz_summary = Column(Text, nullable=True, comment="业务诉求摘要")
    ai_failure_note = Column(Text, nullable=True, comment="AI未解决问题记录")
    ai_solved = Column(SmallInteger, nullable=False, default=0,
                       comment="AI是否解决：0-否 1-是")

    dialogues = relationship("DialogueDetail", back_populates="order",
                             cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("instance_id", "conversation_id",
                         name="uk_instance_conversation"),
        Index("idx_order_phone", "phone"),
        Index("idx_order_type_status", "order_type", "order_status"),
        Index("idx_order_created_time", "created_time"),
        Index("idx_order_agent_id", "agent_id"),
    )


class DialogueDetail(Base):
    """对话明细表 —— 每一条话都会保存"""
    __tablename__ = "dialogue_detail"

    dia_id = Column(BigInteger, primary_key=True, autoincrement=True,
                    comment="对话明细主键")
    order_id = Column(BigInteger, ForeignKey("work_order.order_id"),
                      nullable=False, comment="关联工单ID")
    content = Column(Text, nullable=False, comment="语音转写文本内容")
    role = Column(String(20), nullable=False,
                  comment="发言角色：AI / user / worker / ivr")
    msg_time = Column(DateTime, nullable=False, default=datetime.now,
                      comment="消息时间")

    order = relationship("WorkOrder", back_populates="dialogues")

    __table_args__ = (
        Index("idx_order_role_time", "order_id", "role", "msg_time"),
    )


class AgentInfo(Base):
    """坐席表"""
    __tablename__ = "agent_info"

    agent_id = Column(BigInteger, primary_key=True, autoincrement=True,
                      comment="坐席主键")
    agent_name = Column(String(50), nullable=False, comment="坐席姓名")
    agent_status = Column(SmallInteger, nullable=False, default=0,
                          comment="坐席状态：0-离线 1-忙碌 2-在线")
    ccc_agent_id = Column(String(100), nullable=True,
                          comment="CCC平台坐席ID（如 agent@instance-id），"
                                  "用于回调事件中 agentId 映射到本地 agent_id")

    __table_args__ = (
        Index("idx_agent_status", "agent_status"),
        Index("idx_agent_ccc_id", "ccc_agent_id"),
    )


class QualityInspection(Base):
    """质检记录表 —— 每条对话对应一条质检记录"""
    __tablename__ = "quality_inspection"

    inspection_id = Column(BigInteger, primary_key=True, autoincrement=True,
                           comment="质检记录主键")
    order_id = Column(BigInteger, ForeignKey("work_order.order_id"),
                      nullable=False, comment="关联工单ID")
    dia_id = Column(BigInteger, ForeignKey("dialogue_detail.dia_id"),
                    nullable=False, comment="关联对话明细ID")
    content = Column(JSONB, nullable=False,
                     comment="消息快照JSON：{content, role, msg_time}")
    evaluation = Column(Text, nullable=True,
                        comment="评价内容（初始为空，质检员手动填写）")
    inspection_status = Column(SmallInteger, nullable=False, default=0,
                               comment="质检状态：0-待评价 1-已评价")

    order = relationship("WorkOrder")
    dialogue = relationship("DialogueDetail")

    __table_args__ = (
        Index("idx_qi_order_id", "order_id"),
        Index("idx_qi_dia_id", "dia_id"),
        Index("idx_qi_status", "inspection_status"),
        UniqueConstraint("order_id", "dia_id", name="idx_qi_order_dia"),
    )


class KnowledgeBaseFile(Base):
    """知识库文件表 —— 记录上传的知识库文件元信息"""
    __tablename__ = "knowledge_base_files"

    file_id = Column(BigInteger, primary_key=True, autoincrement=True,
                     comment="文件主键")
    file_name = Column(String(255), nullable=False, comment="原始文件名")
    file_path = Column(String(500), nullable=False, comment="服务器存储路径")
    file_type = Column(String(20), nullable=False,
                       comment="文件类型：xlsx / pdf / txt / docx / csv")
    file_size = Column(BigInteger, nullable=False, comment="文件大小（字节）")
    status = Column(SmallInteger, nullable=False, default=1,
                    comment="状态：0-处理中 1-已启用 2-已停用")
    upload_time = Column(DateTime, nullable=False, default=datetime.now,
                         comment="上传时间")
    description = Column(String(500), nullable=True, comment="文件描述/备注")

    __table_args__ = (
        Index("idx_kbf_status", "status"),
        Index("idx_kbf_upload_time", "upload_time"),
    )


# ── 引擎 & 会话工厂 ──────────────────────────────────────────
engine = create_engine(settings.pg_url, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(drop_existing: bool = False):
    """
    建表
    - drop_existing=False（默认/生产）：仅创建不存在的表，不删除任何数据
    - drop_existing=True（测试/开发）：先删表再重建（会清空所有数据）
    """
    if drop_existing:
        with engine.connect() as conn:
            for old_table in ("orders", "agents"):
                conn.execute(text(f'DROP TABLE IF EXISTS "{old_table}" CASCADE'))
            conn.commit()
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def get_db():
    """FastAPI 依赖注入：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()