package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.time.OffsetDateTime;

/**
 * CCC 回调请求顶层结构。
 *
 * <p>所有 CCC 回调事件的共同基类，包含 3 个公共字段。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>继承链：CccCallbackRequest → CccAgentEventData → CccCallEventData → 各事件特有 DTO</p>
 */
@Data
@JsonInclude(JsonInclude.Include.NON_NULL)
public class CccCallbackRequest {

    /**
     * 事件时间（格林威治时间，ISO 8601 格式）。
     * 示例值：2021-04-14T02:34:00.447Z
     */
    @JsonProperty("eventTime")
    private OffsetDateTime eventTime;

    /**
     * 事件类型。
     * 示例值：Ringing、Established、Released 等，对应 {@link CccEventType}
     */
    @JsonProperty("eventType")
    private String eventType;

    /**
     * 呼叫中心实例 ID。
     * 示例值：report-test-2
     */
    @JsonProperty("instanceId")
    private String instanceId;
}
