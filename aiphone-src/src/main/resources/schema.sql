-- ==============================================
-- AIPhone 数据库建表脚本（幂等，启动自动执行）
-- 严格对齐 docs/数据库.md
-- ==============================================

-- ==============================================
-- 1. 主工单表
-- ==============================================
CREATE TABLE IF NOT EXISTS work_order (
    order_id BIGSERIAL PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL,
    instance_id VARCHAR(64) NOT NULL,
    ent_name VARCHAR(100),
    ent_address VARCHAR(500),
    ent_cerdit VARCHAR(18),          -- 保留原文档笔误字段名
    phone VARCHAR(20) NOT NULL,
    contact_name VARCHAR(100),
    order_type SMALLINT NOT NULL,
    order_status SMALLINT NOT NULL DEFAULT 1,
    agent_id BIGINT,
    created_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP,
    call_start_time TIMESTAMP NOT NULL,
    call_end_time TIMESTAMP,
    biz_summary TEXT,
    ai_failure_note TEXT,
    ai_solved SMALLINT DEFAULT 0,
    summary_confirmed SMALLINT DEFAULT 0,
    CONSTRAINT uk_instance_conversation UNIQUE (instance_id, conversation_id)
);

-- 兼容已存在的旧表：若 summary_confirmed 字段缺失则补加（CREATE TABLE IF NOT EXISTS 不会修改已存在表）
ALTER TABLE work_order ADD COLUMN IF NOT EXISTS summary_confirmed SMALLINT DEFAULT 0;

-- ==============================================
-- 2. 对话明细表
-- ==============================================
CREATE TABLE IF NOT EXISTS dialogue_detail (
    dia_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    role VARCHAR(20) NOT NULL,
    msg_time TIMESTAMP(3) NOT NULL,
    CONSTRAINT fk_dialogue_order FOREIGN KEY (order_id)
        REFERENCES work_order(order_id) ON DELETE CASCADE
);

-- ==============================================
-- 3. 坐席表
-- ==============================================
CREATE TABLE IF NOT EXISTS agent_info (
    agent_id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(50) NOT NULL,
    agent_status SMALLINT DEFAULT 0,
    ccc_agent_id VARCHAR(100)         -- CCC 平台坐席ID（agent@instance-id），用于回调事件映射
);

-- 兼容已存在的旧表：若 ccc_agent_id 字段缺失则补加（CREATE TABLE IF NOT EXISTS 不会修改已存在表）
ALTER TABLE agent_info ADD COLUMN IF NOT EXISTS ccc_agent_id VARCHAR(100);

-- ==============================================
-- 4. 索引（全部独立创建，提高查询效率）
-- ==============================================
CREATE INDEX IF NOT EXISTS idx_order_phone ON work_order(phone);
CREATE INDEX IF NOT EXISTS idx_order_type_status ON work_order(order_type, order_status);
CREATE INDEX IF NOT EXISTS idx_order_created_time ON work_order(created_time);
CREATE INDEX IF NOT EXISTS idx_order_agent_id ON work_order(agent_id);

CREATE INDEX IF NOT EXISTS idx_order_role_time ON dialogue_detail(order_id, role, msg_time);

CREATE INDEX IF NOT EXISTS idx_agent_status ON agent_info(agent_status);
CREATE INDEX IF NOT EXISTS idx_agent_ccc_id ON agent_info(ccc_agent_id);

-- ==============================================
-- 4.1 登录用户表
-- ==============================================
CREATE TABLE IF NOT EXISTS app_user (
    user_id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'ADMIN',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_time TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_app_user_enabled ON app_user(enabled);

-- ==============================================
-- 5. 表与字段注释（便于维护）
-- ==============================================
COMMENT ON TABLE work_order IS '主工单表：存储来电工单核心信息';
COMMENT ON COLUMN work_order.order_id IS '工单唯一主键';
COMMENT ON COLUMN work_order.conversation_id IS '会话ID，由CCC平台生成';
COMMENT ON COLUMN work_order.instance_id IS '热线机器人实例ID';
COMMENT ON COLUMN work_order.ent_name IS '企业名称';
COMMENT ON COLUMN work_order.ent_address IS '企业经营地址';
COMMENT ON COLUMN work_order.ent_cerdit IS '统一社会信用代码（原文档笔误字段）';
COMMENT ON COLUMN work_order.phone IS '来电号码';
COMMENT ON COLUMN work_order.contact_name IS '联系人姓名';
COMMENT ON COLUMN work_order.order_type IS '工单类型：0-转播 1-咨询 2-投诉 3-回访';
COMMENT ON COLUMN work_order.order_status IS '工单状态：0-主动挂断 1-处理中 2-已办结 3-待回访 4-排队中 5-振铃中';
COMMENT ON COLUMN work_order.agent_id IS '受理坐席ID';
COMMENT ON COLUMN work_order.created_time IS '工单创建时间';
COMMENT ON COLUMN work_order.update_time IS '最后更新时间';
COMMENT ON COLUMN work_order.call_start_time IS '通话开始时间';
COMMENT ON COLUMN work_order.call_end_time IS '通话结束时间';
COMMENT ON COLUMN work_order.biz_summary IS '业务诉求摘要';
COMMENT ON COLUMN work_order.ai_failure_note IS 'AI未解决问题记录';
COMMENT ON COLUMN work_order.ai_solved IS 'AI是否解决：0-否 1-是';
COMMENT ON COLUMN work_order.summary_confirmed IS '业务摘要是否已确认：0-否 1-是';

COMMENT ON TABLE dialogue_detail IS '对话明细表：存储每条语音转写内容';
COMMENT ON COLUMN dialogue_detail.dia_id IS '对话明细主键';
COMMENT ON COLUMN dialogue_detail.order_id IS '关联工单ID';
COMMENT ON COLUMN dialogue_detail.content IS '语音转写文本内容';
COMMENT ON COLUMN dialogue_detail.role IS '发言角色：AI/user/worker/ivr提示';
COMMENT ON COLUMN dialogue_detail.msg_time IS '消息时间（毫秒精度）';

COMMENT ON TABLE agent_info IS '坐席表：客服人员基础信息';
COMMENT ON COLUMN agent_info.agent_id IS '坐席主键';
COMMENT ON COLUMN agent_info.agent_name IS '坐席姓名';
COMMENT ON COLUMN agent_info.agent_status IS '坐席状态：0-离线 1-正忙 2-在线空闲（以数据库.md 注释为准）';
COMMENT ON COLUMN agent_info.ccc_agent_id IS 'CCC 平台坐席ID（如 agent@instance-id），用于回调事件中 agentId 映射到本地 agent_id';

COMMENT ON TABLE app_user IS '系统登录用户表';
COMMENT ON COLUMN app_user.username IS '唯一登录账号';
COMMENT ON COLUMN app_user.password_hash IS 'BCrypt 密码哈希，不保存明文密码';
