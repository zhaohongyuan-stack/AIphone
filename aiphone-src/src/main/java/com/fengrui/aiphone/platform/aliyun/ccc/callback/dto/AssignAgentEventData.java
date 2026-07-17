package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC AssignAgent（分配坐席）事件数据。
 *
 * <p>触发场景：通话成功分配到坐席（排队结束后分配坐席）。
 * 文档来源：测试分析2</p>
 *
 * <p>我方处理：将 agentId 缓存到 Redis（key=ccc:contact:{contactId}:agent），
 * 待 Established 创建工单后关联到 work_order.agent_id。</p>
 *
 * <p>注：agentId 和 skillGroupId 已在父类 {@link CccAgentEventData} 和 {@link CccCallEventData} 中定义。</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class AssignAgentEventData extends CccCallEventData {

    /**
     * 队列类型。
     * 可选值：SkillGroup（技能组）/ Agent（坐席）
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
