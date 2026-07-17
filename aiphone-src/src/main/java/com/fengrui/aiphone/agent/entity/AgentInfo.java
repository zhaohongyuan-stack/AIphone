package com.fengrui.aiphone.agent.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

/**
 * 坐席表实体。
 * <p>agent_status：0-离线 1-正忙 2-在线空闲（以数据库.md 注释为准）</p>
 */
@Data
@TableName("agent_info")
public class AgentInfo {

    @TableId(type = IdType.AUTO)
    private Long agentId;

    private String agentName;
    private Integer agentStatus;

    /**
     * CCC 平台坐席ID（格式：agent@instance-id）。
     * <p>用于 CCC 回调事件中 agentId（字符串）到本地 agent_id（BIGINT）的映射。</p>
     */
    private String cccAgentId;
}
