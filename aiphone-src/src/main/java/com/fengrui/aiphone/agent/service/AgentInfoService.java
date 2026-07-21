package com.fengrui.aiphone.agent.service;

import com.fengrui.aiphone.agent.dto.req.AgentStatusUpdateReq;
import com.fengrui.aiphone.agent.entity.AgentInfo;
import com.fengrui.aiphone.agent.vo.AgentAcceptVO;
import com.fengrui.aiphone.agent.vo.AgentCompleteVO;
import com.fengrui.aiphone.agent.vo.AgentStatusUpdateVO;
import com.fengrui.aiphone.agent.vo.AgentVO;

import java.util.List;

/**
 * 坐席服务接口。
 */
public interface AgentInfoService {

    /**
     * 更新坐席状态：先更新 DB，再更新 Redis 缓存，最后同步 CCC。
     */
    AgentStatusUpdateVO updateStatus(AgentStatusUpdateReq req);

    /**
     * 便捷重载：CCC 坐席事件（AgentCheckIn/Ready/Break/CheckOut）同步状态。
     * <p>CCC 的 agentId 为字符串格式（agent@instance-id），与本地 agent_info.agent_id（Long）不同。
     * 先更新 Redis 缓存（key=agent:status:{cccAgentId}），
     * 再通过 ccc_agent_id 查询本地 agent_id 并同步 DB。</p>
     *
     * @param cccAgentId CCC 坐席 ID（格式：agent@instance-id）
     * @param status     目标状态（0-离线 1-正忙 2-在线空闲）
     */
    void updateStatus(String cccAgentId, Integer status);

    /**
     * 通过 CCC 坐席ID 查询本地坐席信息。
     *
     * @param cccAgentId CCC 坐席ID（格式：agent@instance-id）
     * @return 本地坐席信息，未找到返回 null
     */
    AgentInfo findByCccAgentId(String cccAgentId);

    /**
     * 查询全量坐席列表（供前端下拉选）。
     */
    List<AgentVO> listAgents();

    /**
     * 坐席接单（Python 端调用：事务性更新 work_order + agent_info）。
     * <p>更新 work_order.agent_id / call_start_time / order_status=1，
     * 同时更新 agent_info.agent_status=1（正忙）。</p>
     */
    AgentAcceptVO acceptOrder(Long agentId, Long orderId);

    /**
     * 坐席办结（Python 端调用：事务性更新 work_order + agent_info）。
     * <p>更新 work_order.biz_summary / call_end_time / order_status=2 / ai_solved=0，
     * 同时更新 agent_info.agent_status=2（在线空闲）。</p>
     */
    AgentCompleteVO completeOrder(Long orderId, Long agentId, String manualSummary);
}
