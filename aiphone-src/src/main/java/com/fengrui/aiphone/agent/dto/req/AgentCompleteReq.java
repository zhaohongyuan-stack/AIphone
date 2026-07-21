package com.fengrui.aiphone.agent.dto.req;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 坐席办结请求（Python 端调用）。
 */
@Data
public class AgentCompleteReq {

    @NotNull(message = "orderId 不能为空")
    private Long orderId;

    @NotNull(message = "agentId 不能为空")
    private Long agentId;

    private String manualSummary;  // 人工摘要（可选，Python 端 LLM 生成后传入）
}
