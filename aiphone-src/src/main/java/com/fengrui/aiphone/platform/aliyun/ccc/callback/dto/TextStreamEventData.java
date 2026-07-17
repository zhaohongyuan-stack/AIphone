package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.util.List;

/**
 * CCC TextStream（实时文本流）事件数据。
 *
 * <p>触发场景：ASR 实时识别结果推送（CCC 自带 ASR）。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>我方处理：仅当 {@link #finished}=true 时，调用 {@code DialogueService.saveAndPush}
 * 将识别文本落库 + SSE 推送；中间结果（finished=false）仅打 DEBUG 日志。</p>
 *
 * <p>核心价值：实时字幕推送（接听字幕）。</p>
 *
 * <p>真实消息字段（2026-07-08 联调确认）：
 * agentId / asrTaskId / beginOffsetMS / beginTime / beginTimeMS / callType / callee /
 * caller / channelId / channelName / channelType / contactId / customerId / endOffsetMS /
 * eventTime / eventType / extraInfo / finished / instanceId / mediaType / skillGroupId /
 * text / wordInfoList</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class TextStreamEventData extends CccCallEventData {

    /**
     * ASR 任务 ID。
     * <p>CCC ASR 任务的唯一标识，可用于关联同一次识别任务的多个结果。</p>
     * 示例值：816a968a7f8744029a2e520469572213
     */
    @JsonProperty("asrTaskId")
    private String asrTaskId;

    /**
     * 话务通道类型。
     * <p>用于区分发言角色：{@code agent}（坐席）/ {@code customer}（客户）。
     * 对话明细 role 字段据此映射：agent→worker，customer→user。</p>
     * 示例值：agent
     */
    @JsonProperty("channelType")
    private String channelType;

    /**
     * 通道名称（与 channelId 对应的可读名称）。
     * 示例值：ch-user-057123679680-80915314-1783482586474-job-xxx
     */
    @JsonProperty("channelName")
    private String channelName;

    /**
     * 客户 ID（通常等于 caller）。
     * 示例值：057123679680
     */
    @JsonProperty("customerId")
    private String customerId;

    /**
     * ASR 识别结果文本。
     * 示例值：然后呢。
     */
    @JsonProperty("text")
    private String text;

    /**
     * 一句话是否结束。
     * <p>文档标注 Integer（0/1），JSON 示例为 boolean（true）。
     * 采用 {@code Boolean} 类型兼容两种情况（Jackson 默认支持 Integer→Boolean 强转）。</p>
     * 示例值：true
     */
    @JsonProperty("finished")
    private Boolean finished;

    /**
     * 句子开始时间偏移（毫秒，相对于通话开始）。
     * 示例值：10859
     */
    @JsonProperty("beginOffsetMS")
    private Long beginOffsetMS;

    /**
     * 句子结束时间偏移（毫秒，相对于通话开始）。
     * 示例值：11986
     */
    @JsonProperty("endOffsetMS")
    private Long endOffsetMS;

    /**
     * 句子开始时间（UTC ISO 8601）。
     * 示例值：2026-07-08T03:49:59.314Z
     */
    @JsonProperty("beginTime")
    private String beginTime;

    /**
     * 句子开始时间（毫秒时间戳）。
     * 示例值：1783482599314
     */
    @JsonProperty("beginTimeMS")
    private Long beginTimeMS;

    /**
     * 附加信息（语速、情绪等）。
     * 示例值：speechRate=76;emotionIndex=0
     */
    @JsonProperty("extraInfo")
    private String extraInfo;

    /**
     * 词级时间戳信息列表（用于精细展示）。
     */
    @JsonProperty("wordInfoList")
    private List<WordInfo> wordInfoList;

    /**
     * 词级时间戳信息。
     */
    @Data
    public static class WordInfo {
        /** 词开始时间偏移（毫秒） */
        @JsonProperty("beginOffsetMS")
        private Long beginOffsetMS;

        /** 词结束时间偏移（毫秒） */
        @JsonProperty("endOffsetMS")
        private Long endOffsetMS;

        /** 词文本 */
        @JsonProperty("word")
        private String word;
    }
}
