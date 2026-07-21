package com.fengrui.aiphone.agent.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 坐席接单返回值。
 */
@Data
public class AgentAcceptVO {
    private Long orderId;
    private Long agentId;
    private Integer agentStatus;
    private LocalDateTime callStartTime;
}
