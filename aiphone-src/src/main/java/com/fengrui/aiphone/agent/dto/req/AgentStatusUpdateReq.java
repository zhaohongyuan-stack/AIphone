package com.fengrui.aiphone.agent.dto.req;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 坐席状态变更请求。
 */
@Data
public class AgentStatusUpdateReq {

    @NotNull(message = "agentId 不能为空")
    private Long agentId;

    @NotNull(message = "agentStatus 不能为空")
    private Integer agentStatus;
}
