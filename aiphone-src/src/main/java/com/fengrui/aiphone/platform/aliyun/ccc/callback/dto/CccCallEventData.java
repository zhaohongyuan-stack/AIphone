package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC 话务类事件数据（= 通话上下文 CallContext）。
 *
 * <p>继承 {@link CccAgentEventData}，增加话务类事件公共字段（11 个）。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>所有话务事件（Ringing/Established/Released/Dialing 等）均继承此类。
 * 这 11 个字段即为「通话上下文」概念，对应 {@code ChannelContext}（通道上下文）。</p>
 *
 * <p>关键字段说明：
 * <ul>
 *   <li>{@link #contactId}：话务 ID（job-xxx 格式），对应我方 {@code work_order.conversation_id}</li>
 *   <li>{@link #channelId}：通话通道 ID，一通电话可能有多个通道（坐席通道 + 客户通道）</li>
 *   <li>{@link #callType}：呼叫类型枚举（INBOUND/OUTBOUND/INTERNAL 等）</li>
 * </ul></p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class CccCallEventData extends CccAgentEventData {

    /**
     * 话务 ID（即 jobId）。
     * <p>对应我方 {@code work_order.conversation_id} 字段，用于关联工单。</p>
     * 示例值：job-f8e9639a-81b8-4740-8af7-c13cc1553919
     */
    @JsonProperty("contactId")
    private String contactId;

    /**
     * 通话通道 ID。
     * <p>一通电话可能包含多个通道（如坐席通道和客户通道）。</p>
     * 示例值：19aafd79-ba0c-4102-8e58-9a699d4e5811
     */
    @JsonProperty("channelId")
    private String channelId;

    /**
     * 呼叫类型。
     * 可选值：INTERNAL/INBOUND/OUTBOUND/CONFERENCE/BACK2BACK/PREDICTIVE/CONSULTANT/MONITOR/COACH/BARGE/INTERCEPT
     * 示例值：INBOUND
     */
    @JsonProperty("callType")
    private String callType;

    /**
     * 主叫号码。
     * 示例值：1388888****
     */
    @JsonProperty("caller")
    private String caller;

    /**
     * 被叫号码。
     * 示例值：0111234****
     */
    @JsonProperty("callee")
    private String callee;

    /**
     * 媒体类型。
     * 可选值：AUDIO（音频）/VIDEO（视频）/CHAT（消息）/TICKET（工单）
     * <p>注：真实消息中大写，早期文档标注为 Audio，实际以大写为准。</p>
     * 示例值：AUDIO
     */
    @JsonProperty("mediaType")
    private String mediaType;

    /**
     * 技能组 ID。
     * <p>真实消息中话务事件会携带 skillGroupId（如 zonghezixun@demo-xxx）。</p>
     * 示例值：zonghezixun@demo-1334882287961657
     */
    @JsonProperty("skillGroupId")
    private String skillGroupId;

    /**
     * 中间号码。
     * 示例值：05712910xxxx
     */
    @JsonProperty("broker")
    private String broker;

    /**
     * 附加中间号码。
     * <p>如果该参数存在，则呼叫 callee 时使用该参数指定的号码。</p>
     * 示例值：05712910xxxx
     */
    @JsonProperty("additionalBroker")
    private String additionalBroker;

    /**
     * 自定义话务相关数据（JSON 字符串）。
     * 示例值：{"key":"value"}
     */
    @JsonProperty("callVariables")
    private String callVariables;

    /**
     * 接入渠道 ID（当媒体类型是 Chat 和 Ticket 时才会有值）。
     * 示例值：f8e9639a-81b8-4740-8af7-c13cc1553919
     */
    @JsonProperty("accessChannelId")
    private String accessChannelId;

    /**
     * 接入渠道类型（当媒体类型是 Chat 和 Ticket 时才会有值）。
     * 示例值：Web
     */
    @JsonProperty("accessChannelType")
    private String accessChannelType;

    /**
     * 接入渠道名称（当媒体类型是 Chat 和 Ticket 时才会有值）。
     * 示例值：测试渠道1
     */
    @JsonProperty("accessChannelName")
    private String accessChannelName;
}
