-- ============================================================================
-- 智能对话机器人坐席状态维护 SQL
-- 对齐阿里云 CCC 2.0 坐席事件格式（AgentCheckIn/AgentReady/AgentBreak/AgentCheckOut 等）
-- 参考文档: https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats
--
-- agent_status 枚举: 0=离线(签出)  1=忙碌(通话中/小休)  2=在线空闲(已就绪)
-- 与 tests/conftest.py + core/redis_manager.py 的槽位管理配合使用
-- ============================================================================

-- ── 建表 ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS robot_agent (
    id                SERIAL PRIMARY KEY,
    agent_name        VARCHAR(50)  NOT NULL,                             -- 机器人坐席名称
    agent_status      SMALLINT     NOT NULL DEFAULT 0,                   -- 0=离线 1=忙碌 2=在线空闲
    slot_id           INT          NOT NULL,                             -- 对应 Redis 槽位编号 (robot:slot:{slot_id})
    ccc_agent_id      VARCHAR(100),                                      -- CCC 平台坐席ID（如 robot@ccc-instance）
    skill_group_id    VARCHAR(100),                                      -- 签入技能组ID（如 skg-default@ccc-instance）
    skill_level       INT          DEFAULT 5,                            -- 技能组等级
    work_mode         VARCHAR(20)  DEFAULT 'ON_SITE',                    -- 工作模式: ON_SITE / OFF_SITE
    device_id         VARCHAR(100),                                      -- 设备ID（SIP话机设备）
    chat_device_id    VARCHAR(100),                                      -- Chat设备ID
    max_slots         INT          DEFAULT 10,                           -- 最大并发处理数
    outbound_scenario SMALLINT     DEFAULT 0,                            -- 是否仅外呼模式: 0=否 1=是
    break_code        VARCHAR(50),                                       -- 小休代码（如 Warm-up, Lunch, Meeting）
    contact_id        VARCHAR(100),                                      -- 当前话务ID
    channel_id        VARCHAR(100),                                      -- 当前通话通道ID
    call_type         VARCHAR(20),                                       -- 呼叫类型: INBOUND/OUTBOUND/INTERNAL 等
    ringing_slots     INT          DEFAULT 0,                            -- 当前振铃会话数
    talking_slots     INT          DEFAULT 0,                            -- 当前通话会话数
    last_event        VARCHAR(50),                                       -- 最后事件类型 (AgentCheckIn/AgentReady/...)
    last_event_time   TIMESTAMP,                                         -- 最后事件时间
    check_in_time     TIMESTAMP,                                         -- 签入时间
    created_time      TIMESTAMP    DEFAULT NOW(),
    updated_time      TIMESTAMP    DEFAULT NOW()
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_robot_agent_status   ON robot_agent (agent_status);
CREATE INDEX IF NOT EXISTS idx_robot_agent_slot_id  ON robot_agent (slot_id);
CREATE INDEX IF NOT EXISTS idx_robot_agent_ccc_id   ON robot_agent (ccc_agent_id);


-- ============================================================================
--  自动化维护语句（供后端代码 / 定时任务 / CCC 事件回调调用）
-- ============================================================================

-- ────────────────────────────────────────────────────────────────────────────
--  1. 初始化机器人坐席（根据 config.ROBOT_SLOT_COUNT 创建对应数量的坐席）
--     用法: SELECT init_robot_agents(3);  -- 创建3个机器人坐席
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION init_robot_agents(slot_count INT DEFAULT 3)
RETURNS TABLE(agent_id INT, agent_name VARCHAR, slot_id INT) AS $$
DECLARE
    i INT;
    new_id INT;
BEGIN
    FOR i IN 1..slot_count LOOP
        -- 仅当该 slot_id 不存在时才插入
        IF NOT EXISTS (SELECT 1 FROM robot_agent WHERE slot_id = i) THEN
            INSERT INTO robot_agent (agent_name, agent_status, slot_id, max_slots)
            VALUES ('机器人坐席-' || i, 0, i, 10)
            RETURNING id INTO new_id;
            agent_id := new_id;
            agent_name := '机器人坐席-' || i;
            slot_id := i;
            RETURN NEXT;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────────────────────
--  2. 坐席签入 (AgentCheckIn)
--     CCC 事件字段: agentId, skillGroupIds, skillLevels, workMode, deviceId,
--                   chatDeviceId, maxSlots, additivity
--     用法: SELECT robot_agent_check_in('robot@ccc-instance', 'skg-default@ccc-instance', 5, 'ON_SITE', 'CCC-chrome-xxx', 'chat-xxx', 10);
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION robot_agent_check_in(
    p_ccc_agent_id    VARCHAR,
    p_skill_group_id  VARCHAR DEFAULT NULL,
    p_skill_level     INT     DEFAULT 5,
    p_work_mode       VARCHAR DEFAULT 'ON_SITE',
    p_device_id       VARCHAR DEFAULT NULL,
    p_chat_device_id  VARCHAR DEFAULT NULL,
    p_max_slots       INT     DEFAULT 10
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
BEGIN
    -- 按 ccc_agent_id 查找，找不到则按 slot_id 自动分配
    SELECT * INTO v_agent FROM robot_agent WHERE ccc_agent_id = p_ccc_agent_id;
    IF NOT FOUND THEN
        -- 新坐席：找一个未签入的 slot
        SELECT * INTO v_agent FROM robot_agent
         WHERE ccc_agent_id IS NULL AND agent_status = 0
         ORDER BY slot_id LIMIT 1;
        IF NOT FOUND THEN
            RETURN QUERY SELECT 0::INT, 0::SMALLINT, '无可用槽位，请先初始化机器人坐席'::VARCHAR;
            RETURN;
        END IF;
    END IF;

    UPDATE robot_agent SET
        agent_status    = 2,                           -- 在线空闲
        ccc_agent_id    = p_ccc_agent_id,
        skill_group_id  = COALESCE(p_skill_group_id, skill_group_id),
        skill_level     = p_skill_level,
        work_mode       = p_work_mode,
        device_id       = COALESCE(p_device_id, device_id),
        chat_device_id  = COALESCE(p_chat_device_id, chat_device_id),
        max_slots       = p_max_slots,
        last_event      = 'AgentCheckIn',
        last_event_time = NOW(),
        check_in_time   = NOW(),
        updated_time    = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, 2::SMALLINT, '签入成功'::VARCHAR;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────────────────────
--  3. 坐席就绪 (AgentReady)
--     CCC 事件字段: agentId, skillGroupIds, outboundScenario
--     用法: SELECT robot_agent_ready('robot@ccc-instance', 0);
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION robot_agent_ready(
    p_ccc_agent_id      VARCHAR,
    p_outbound_scenario  SMALLINT DEFAULT 0
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
BEGIN
    SELECT * INTO v_agent FROM robot_agent WHERE ccc_agent_id = p_ccc_agent_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 0::INT, 0::SMALLINT, '坐席不存在'::VARCHAR;
        RETURN;
    END IF;

    UPDATE robot_agent SET
        agent_status       = 2,                        -- 在线空闲
        outbound_scenario  = p_outbound_scenario,
        last_event         = 'AgentReady',
        last_event_time    = NOW(),
        updated_time       = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, 2::SMALLINT, '坐席已就绪'::VARCHAR;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────────────────────
--  4. 坐席小休 (AgentBreak)
--     CCC 事件字段: agentId, breakCode
--     用法: SELECT robot_agent_break('robot@ccc-instance', 'Lunch');
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION robot_agent_break(
    p_ccc_agent_id  VARCHAR,
    p_break_code    VARCHAR DEFAULT 'Warm-up'
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
BEGIN
    SELECT * INTO v_agent FROM robot_agent WHERE ccc_agent_id = p_ccc_agent_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 0::INT, 0::SMALLINT, '坐席不存在'::VARCHAR;
        RETURN;
    END IF;

    UPDATE robot_agent SET
        agent_status    = 1,                            -- 忙碌（小休）
        break_code      = p_break_code,
        last_event      = 'AgentBreak',
        last_event_time = NOW(),
        updated_time    = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, 1::SMALLINT, '坐席已小休: ' || p_break_code;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────────────────────
--  5. 坐席签出 (AgentCheckOut)
--     CCC 事件: 无特有字段，继承公有字段
--     用法: SELECT robot_agent_check_out('robot@ccc-instance');
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION robot_agent_check_out(
    p_ccc_agent_id VARCHAR
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
BEGIN
    SELECT * INTO v_agent FROM robot_agent WHERE ccc_agent_id = p_ccc_agent_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 0::INT, 0::SMALLINT, '坐席不存在'::VARCHAR;
        RETURN;
    END IF;

    UPDATE robot_agent SET
        agent_status    = 0,                            -- 离线
        contact_id      = NULL,
        channel_id      = NULL,
        call_type       = NULL,
        ringing_slots   = 0,
        talking_slots   = 0,
        break_code      = NULL,
        last_event      = 'AgentCheckOut',
        last_event_time = NOW(),
        check_in_time   = NULL,
        updated_time    = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, 0::SMALLINT, '坐席已签出'::VARCHAR;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────────────────────
--  6. 坐席开始通话 (AgentTalk) — 对应 Redis occupy_slot
--     CCC 事件字段: agentId, contactId, channelId, callType, skillGroupId,
--                   scenario, mediaType, maxSlots, ringingSlots, talkingSlots
--     用法: SELECT robot_agent_talk('robot@ccc-instance', 'job-xxx', 'ch-xxx', 'INBOUND', 'skg-default@ccc');
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION robot_agent_talk(
    p_ccc_agent_id    VARCHAR,
    p_contact_id      VARCHAR,
    p_channel_id      VARCHAR DEFAULT NULL,
    p_call_type       VARCHAR DEFAULT 'INBOUND',
    p_skill_group_id  VARCHAR DEFAULT NULL,
    p_ringing_slots   INT     DEFAULT 0,
    p_talking_slots   INT     DEFAULT 1
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
BEGIN
    -- 同时支持按 ccc_agent_id 或 slot_id 查找
    SELECT * INTO v_agent FROM robot_agent WHERE ccc_agent_id = p_ccc_agent_id;
    IF NOT FOUND THEN
        -- 尝试按 slot_id 查找（p_ccc_agent_id 可能是 slot_id 的数字）
        BEGIN
            SELECT * INTO v_agent FROM robot_agent WHERE slot_id = p_ccc_agent_id::INT;
        EXCEPTION WHEN OTHERS THEN
            RETURN QUERY SELECT 0::INT, 0::SMALLINT, '坐席不存在'::VARCHAR;
            RETURN;
        END;
    END IF;

    UPDATE robot_agent SET
        agent_status    = 1,                            -- 忙碌
        contact_id      = p_contact_id,
        channel_id      = COALESCE(p_channel_id, channel_id),
        call_type       = p_call_type,
        skill_group_id  = COALESCE(p_skill_group_id, skill_group_id),
        ringing_slots   = p_ringing_slots,
        talking_slots   = p_talking_slots,
        last_event      = 'AgentTalk',
        last_event_time = NOW(),
        updated_time    = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, 1::SMALLINT, '坐席通话中: ' || p_contact_id;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────────────────────
--  7. 坐席释放通话 (AgentRelease) — 对应 Redis release_slot
--     CCC 事件字段: agentId, contactId, channelId, callType, skillGroupId,
--                   scenario, transferee, mediaType, maxSlots, ringingSlots, talkingSlots
--     用法: SELECT robot_agent_release('robot@ccc-instance');
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION robot_agent_release(
    p_ccc_agent_id  VARCHAR,
    p_transferee    VARCHAR DEFAULT NULL
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
BEGIN
    SELECT * INTO v_agent FROM robot_agent WHERE ccc_agent_id = p_ccc_agent_id;
    IF NOT FOUND THEN
        BEGIN
            SELECT * INTO v_agent FROM robot_agent WHERE slot_id = p_ccc_agent_id::INT;
        EXCEPTION WHEN OTHERS THEN
            RETURN QUERY SELECT 0::INT, 0::SMALLINT, '坐席不存在'::VARCHAR;
            RETURN;
        END;
    END IF;

    UPDATE robot_agent SET
        agent_status    = 2,                            -- 回到在线空闲
        contact_id      = NULL,
        channel_id      = NULL,
        call_type       = NULL,
        ringing_slots   = 0,
        talking_slots   = 0,
        last_event      = 'AgentRelease',
        last_event_time = NOW(),
        updated_time    = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, 2::SMALLINT,
        '坐席已释放通话' || CASE WHEN p_transferee IS NOT NULL
            THEN ' (转接至 ' || p_transferee || ')' ELSE '' END;
END;
$$ LANGUAGE plpgsql;


-- ────────────────────────────────────────────────────────────────────────────
--  8. 坐席振铃 (AgentRinging) — 通话分配但尚未应答
--     用法: SELECT robot_agent_ringing('robot@ccc-instance', 'job-xxx', 'ch-xxx', 'INBOUND');
-- ────────────────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION robot_agent_ringing(
    p_ccc_agent_id    VARCHAR,
    p_contact_id      VARCHAR,
    p_channel_id      VARCHAR DEFAULT NULL,
    p_call_type       VARCHAR DEFAULT 'INBOUND',
    p_skill_group_id  VARCHAR DEFAULT NULL,
    p_ringing_slots   INT     DEFAULT 1,
    p_talking_slots   INT     DEFAULT 0
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
BEGIN
    SELECT * INTO v_agent FROM robot_agent WHERE ccc_agent_id = p_ccc_agent_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 0::INT, 0::SMALLINT, '坐席不存在'::VARCHAR;
        RETURN;
    END IF;

    UPDATE robot_agent SET
        agent_status    = 1,                            -- 忙碌（振铃中）
        contact_id      = p_contact_id,
        channel_id      = COALESCE(p_channel_id, channel_id),
        call_type       = p_call_type,
        skill_group_id  = COALESCE(p_skill_group_id, skill_group_id),
        ringing_slots   = p_ringing_slots,
        talking_slots   = p_talking_slots,
        last_event      = 'AgentRinging',
        last_event_time = NOW(),
        updated_time    = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, 1::SMALLINT, '坐席振铃中: ' || p_contact_id;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
--  查询视图（供前端大盘 / DBA 手工查询）
-- ============================================================================

-- ── 9. 查看所有机器人坐席状态 ──────────────────────────────────────────────

-- SELECT * FROM v_robot_agent_status;

CREATE OR REPLACE VIEW v_robot_agent_status AS
SELECT
    id,
    agent_name,
    slot_id,
    CASE agent_status
        WHEN 0 THEN '离线'
        WHEN 1 THEN '忙碌'
        WHEN 2 THEN '在线空闲'
        ELSE '未知'
    END AS status_text,
    agent_status,
    ccc_agent_id,
    skill_group_id,
    skill_level,
    work_mode,
    max_slots,
    (ringing_slots + talking_slots) AS current_slots,
    call_type,
    contact_id,
    break_code,
    last_event,
    last_event_time,
    check_in_time,
    EXTRACT(EPOCH FROM (NOW() - check_in_time))::INT AS online_duration_sec
FROM robot_agent
ORDER BY slot_id;


-- ── 10. 统计概览：在线/忙碌/离线数量 ────────────────────────────────────────

-- SELECT * FROM v_robot_agent_summary;

CREATE OR REPLACE VIEW v_robot_agent_summary AS
SELECT
    COUNT(*)                                                       AS total,
    COUNT(*) FILTER (WHERE agent_status = 2)                       AS online_idle,
    COUNT(*) FILTER (WHERE agent_status = 1)                       AS busy,
    COUNT(*) FILTER (WHERE agent_status = 0)                       AS offline,
    COUNT(*) FILTER (WHERE agent_status = 1 AND break_code IS NOT NULL) AS on_break,
    COUNT(*) FILTER (WHERE agent_status = 1 AND contact_id IS NOT NULL) AS in_call,
    COALESCE(SUM(ringing_slots + talking_slots), 0)                AS total_active_sessions,
    COALESCE(SUM(max_slots), 0)                                    AS total_max_slots,
    ROUND(
        CASE WHEN SUM(max_slots) > 0
             THEN SUM(ringing_slots + talking_slots)::NUMERIC / SUM(max_slots)::NUMERIC * 100
             ELSE 0 END, 1
    )                                                               AS load_pct
FROM robot_agent;


-- ── 11. 按 slot_id 更新状态（最简调用，供 Redis 操作同步到 DB）─────────────

-- 用法: SELECT robot_agent_update_by_slot(1, 1, 'job-xxx');  -- 槽位1设为忙碌
--       SELECT robot_agent_update_by_slot(1, 2);             -- 槽位1设为在线空闲
--       SELECT robot_agent_update_by_slot(1, 0);             -- 槽位1设为离线

CREATE OR REPLACE FUNCTION robot_agent_update_by_slot(
    p_slot_id     INT,
    p_status      SMALLINT,
    p_contact_id  VARCHAR DEFAULT NULL
) RETURNS TABLE(id INT, status SMALLINT, msg VARCHAR) AS $$
DECLARE
    v_agent robot_agent%ROWTYPE;
    v_event VARCHAR;
BEGIN
    SELECT * INTO v_agent FROM robot_agent WHERE slot_id = p_slot_id;
    IF NOT FOUND THEN
        RETURN QUERY SELECT 0::INT, 0::SMALLINT, '槽位 ' || p_slot_id || ' 不存在'::VARCHAR;
        RETURN;
    END IF;

    v_event := CASE p_status
        WHEN 0 THEN 'AgentCheckOut'
        WHEN 1 THEN 'AgentTalk'
        WHEN 2 THEN 'AgentReady'
        ELSE 'AgentStatusChange'
    END;

    UPDATE robot_agent SET
        agent_status    = p_status,
        contact_id      = CASE WHEN p_status = 1 THEN COALESCE(p_contact_id, contact_id) ELSE NULL END,
        ringing_slots   = CASE WHEN p_status = 1 THEN 1 ELSE 0 END,
        talking_slots   = CASE WHEN p_status = 1 THEN 1 ELSE 0 END,
        last_event      = v_event,
        last_event_time = NOW(),
        updated_time    = NOW()
    WHERE id = v_agent.id;

    RETURN QUERY SELECT v_agent.id, p_status,
        '槽位 ' || p_slot_id || ' → ' ||
        CASE p_status WHEN 0 THEN '离线' WHEN 1 THEN '忙碌' WHEN 2 THEN '在线空闲' END;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
--  测试数据初始化（对齐 tests/test_data/seed_agents.json 的机器人坐席配置）
--  用法: SELECT init_robot_agents(3);  -- 与 config.ROBOT_SLOT_COUNT 保持一致
--       SELECT robot_agent_check_in('robot_slot_1@ccc-test', 'skg-default@ccc-test', 5, 'ON_SITE', 'CCC-chrome-slot1');
--       SELECT robot_agent_check_in('robot_slot_2@ccc-test', 'skg-default@ccc-test', 5, 'ON_SITE', 'CCC-chrome-slot2');
--       SELECT robot_agent_check_in('robot_slot_3@ccc-test', 'skg-default@ccc-test', 5, 'ON_SITE', 'CCC-chrome-slot3');
-- ============================================================================