package com.fengrui.aiphone.agent.dto.req;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 坐席接单请求（Python 端调用）。
 */
@Data
public class AgentAcceptReq {

    @NotNull(message = "agentId 不能为空")
    private Long agentId;

    @NotNull(message = "orderId 不能为空")
    private Long orderId;
}
