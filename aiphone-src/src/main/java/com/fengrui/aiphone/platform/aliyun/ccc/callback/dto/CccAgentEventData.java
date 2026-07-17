package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC 坐席类事件数据。
 *
 * <p>继承 {@link CccCallbackRequest}，增加坐席类事件公共字段（2 个）。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>所有坐席事件（AgentCheckIn/AgentReady/AgentBreak/AgentCheckOut 等）均继承此类。</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class CccAgentEventData extends CccCallbackRequest {

    /**
     * 签入技能组 ID 列表（逗号分隔）。
     * 示例值：skg-default@report-test-2,skillgroup@report-test-2
     */
    @JsonProperty("skillGroupIds")
    private String skillGroupIds;

    /**
     * 坐席 ID。
     * 示例值：test@report-test-2
     */
    @JsonProperty("agentId")
    private String agentId;
}
