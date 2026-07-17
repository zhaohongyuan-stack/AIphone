package com.fengrui.aiphone.agent.vo;

import lombok.Data;

/**
 * 坐席信息（列表查询用）。
 */
@Data
public class AgentVO {

    private Long agentId;
    private String agentName;
    private Integer agentStatus;
}
