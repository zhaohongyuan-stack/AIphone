package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC Abandoned（放弃）事件数据。
 *
 * <p>触发场景：客户在 IVR 交互、排队或振铃阶段放弃通话。
 * 文档来源：测试分析2</p>
 *
 * <p>我方处理：根据 {@link #abandonPhase} 清理 Redis 缓存，
 * 若已有工单则更新 order_status=0（主动挂断）。</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class AbandonedEventData extends CccCallEventData {

    /**
     * 放弃阶段。
     * 可选值：IVR（IVR交互阶段）/ Queuing（排队阶段）/ Ringing（坐席振铃阶段）
     * 示例值：Queuing
     */
    @JsonProperty("abandonPhase")
    private String abandonPhase;

    /**
     * 联系流 ID。
     * 示例值：b13612f1-e135-0008-0053-d632fdxb3b91e
     */
    @JsonProperty("contactFlowId")
    private String contactFlowId;

    /**
     * 联系流类型。
     * 可选值：MAIN_FLOW（主流程）/ SUB_FLOW（子流程）/ SURVEY_FLOW（满意度调查流程）
     * 示例值：MAIN_FLOW
     */
    @JsonProperty("contactFlowType")
    private String contactFlowType;

    /**
     * 队列类型。
     * 可选值：Agent（坐席）/ SkillGroup（技能组）
     * 示例值：SkillGroup
     */
    @JsonProperty("queueType")
    private String queueType;

    /**
     * 业务标识（当外部调度应用发起主动调度时传入的唯一业务 ID）。
     * 示例值：bizId=j123949
     */
    @JsonProperty("tags")
    private String tags;
}
