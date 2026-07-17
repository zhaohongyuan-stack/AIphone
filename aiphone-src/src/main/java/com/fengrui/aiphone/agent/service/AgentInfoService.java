package com.fengrui.aiphone.agent.service;

import com.fengrui.aiphone.agent.dto.req.AgentStatusUpdateReq;
import com.fengrui.aiphone.agent.entity.AgentInfo;
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
}
