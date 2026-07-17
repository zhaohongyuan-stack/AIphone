package com.fengrui.aiphone.agent.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 坐席状态变更响应。
 */
@Data
public class AgentStatusUpdateVO {

    private Long agentId;
    private Integer agentStatus;
    private LocalDateTime updateTime;
}
