package com.fengrui.aiphone.agent.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 坐席办结返回值。
 */
@Data
public class AgentCompleteVO {
    private Long orderId;
    private Long agentId;
    private Integer agentStatus;
    private String bizSummary;
    private LocalDateTime callEndTime;
}
