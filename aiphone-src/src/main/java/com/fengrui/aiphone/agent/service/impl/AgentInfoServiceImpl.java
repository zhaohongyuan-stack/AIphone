package com.fengrui.aiphone.agent.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fengrui.aiphone.agent.dto.req.AgentStatusUpdateReq;
import com.fengrui.aiphone.agent.entity.AgentInfo;
import com.fengrui.aiphone.agent.mapper.AgentInfoMapper;
import com.fengrui.aiphone.agent.service.AgentInfoService;
import com.fengrui.aiphone.agent.vo.AgentAcceptVO;
import com.fengrui.aiphone.agent.vo.AgentCompleteVO;
import com.fengrui.aiphone.agent.vo.AgentStatusUpdateVO;
import com.fengrui.aiphone.agent.vo.AgentVO;
import com.fengrui.aiphone.common.enums.AgentStatusEnum;
import com.fengrui.aiphone.exception.BusinessException;
import com.fengrui.aiphone.platform.aliyun.ccc.client.CccAgentClient;
import com.fengrui.aiphone.workorder.entity.WorkOrder;
import com.fengrui.aiphone.workorder.mapper.WorkOrderMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 坐席服务实现。
 * <p>状态更新流程：DB -> Redis -> CCC，保证缓存一致性。</p>
 */
@Service
public class AgentInfoServiceImpl implements AgentInfoService {

    private static final Logger log = LoggerFactory.getLogger(AgentInfoServiceImpl.class);

    /** Redis 坐席状态缓存 key 前缀：agent:status:{agentId} */
    private static final String REDIS_KEY_PREFIX = "agent:status:";

    @Autowired
    private AgentInfoMapper agentInfoMapper;

    @Autowired
    private RedisTemplate<String, Object> redisTemplate;

    @Autowired
    private CccAgentClient cccAgentClient;

    @Autowired
    private WorkOrderMapper workOrderMapper;

    @Override
    @Transactional
    public AgentStatusUpdateVO updateStatus(AgentStatusUpdateReq req) {
        AgentInfo agent = agentInfoMapper.selectById(req.getAgentId());
        if (agent == null) {
            throw new BusinessException("坐席不存在: " + req.getAgentId());
        }
        AgentStatusEnum.of(req.getAgentStatus()); // 校验枚举合法性

        // 1. 先更新 DB
        LambdaUpdateWrapper<AgentInfo> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(AgentInfo::getAgentId, req.getAgentId())
               .set(AgentInfo::getAgentStatus, req.getAgentStatus());
        agentInfoMapper.update(null, wrapper);

        // 2. 再更新 Redis 缓存
        String redisKey = REDIS_KEY_PREFIX + req.getAgentId();
        redisTemplate.opsForValue().set(redisKey, req.getAgentStatus());

        // 3. 同步调用 CCC（离线签退，其他签到）
        try {
            if (req.getAgentStatus() == AgentStatusEnum.OFFLINE.getCode()) {
                cccAgentClient.signOutGroup(req.getAgentId());
            } else {
                cccAgentClient.signInGroup(req.getAgentId());
            }
        } catch (Exception e) {
            // CCC 调用失败不影响状态更新，仅记录日志
            log.error("CCC 调用失败，agentId={}, status={}", req.getAgentId(), req.getAgentStatus(), e);
        }

        AgentStatusUpdateVO vo = new AgentStatusUpdateVO();
        vo.setAgentId(req.getAgentId());
        vo.setAgentStatus(req.getAgentStatus());
        vo.setUpdateTime(LocalDateTime.now());
        return vo;
    }

    @Override
    public void updateStatus(String cccAgentId, Integer status) {
        AgentStatusEnum.of(status); // 校验枚举合法性
        String redisKey = REDIS_KEY_PREFIX + cccAgentId;
        redisTemplate.opsForValue().set(redisKey, status);
        log.info("CCC 坐席状态同步 Redis: cccAgentId={}, status={}", cccAgentId, status);
        // 通过 ccc_agent_id 查询本地 agent_id 并同步 DB
        AgentInfo agent = findByCccAgentId(cccAgentId);
        if (agent != null) {
            LambdaUpdateWrapper<AgentInfo> wrapper = new LambdaUpdateWrapper<>();
            wrapper.eq(AgentInfo::getAgentId, agent.getAgentId())
                   .set(AgentInfo::getAgentStatus, status);
            agentInfoMapper.update(null, wrapper);
            log.info("CCC 坐席状态已同步 DB: agentId={}, cccAgentId={}, status={}",
                    agent.getAgentId(), cccAgentId, status);
        } else {
            log.warn("CCC 坐席状态同步：本地未找到对应坐席，仅更新 Redis: cccAgentId={}", cccAgentId);
        }
    }

    @Override
    public AgentInfo findByCccAgentId(String cccAgentId) {
        if (cccAgentId == null || cccAgentId.isBlank()) {
            return null;
        }
        LambdaQueryWrapper<AgentInfo> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(AgentInfo::getCccAgentId, cccAgentId).last("LIMIT 1");
        return agentInfoMapper.selectOne(wrapper);
    }

    @Override
    public List<AgentVO> listAgents() {
        List<AgentInfo> agents = agentInfoMapper.selectList(null);
        return agents.stream().map(a -> {
            AgentVO vo = new AgentVO();
            vo.setAgentId(a.getAgentId());
            vo.setAgentName(a.getAgentName());
            vo.setAgentStatus(a.getAgentStatus());
            return vo;
        }).collect(Collectors.toList());
    }

    @Override
    @Transactional
    public AgentAcceptVO acceptOrder(Long agentId, Long orderId) {
        // 1. 更新工单：关联坐席 + 设置通话开始时间 + 状态处理中
        WorkOrder order = workOrderMapper.selectById(orderId);
        if (order == null) {
            throw new BusinessException("工单不存在: " + orderId);
        }
        LambdaUpdateWrapper<WorkOrder> orderWrapper = new LambdaUpdateWrapper<>();
        orderWrapper.eq(WorkOrder::getOrderId, orderId)
                    .set(WorkOrder::getAgentId, agentId)
                    .set(WorkOrder::getCallStartTime, LocalDateTime.now())
                    .set(WorkOrder::getOrderStatus, 1) // 处理中
                    .set(WorkOrder::getUpdateTime, LocalDateTime.now());
        workOrderMapper.update(null, orderWrapper);

        // 2. 更新坐席状态为正忙
        LambdaUpdateWrapper<AgentInfo> agentWrapper = new LambdaUpdateWrapper<>();
        agentWrapper.eq(AgentInfo::getAgentId, agentId)
                    .set(AgentInfo::getAgentStatus, AgentStatusEnum.BUSY.getCode());
        agentInfoMapper.update(null, agentWrapper);

        // 3. 更新 Redis
        redisTemplate.opsForValue().set(REDIS_KEY_PREFIX + agentId, AgentStatusEnum.BUSY.getCode());

        AgentAcceptVO vo = new AgentAcceptVO();
        vo.setOrderId(orderId);
        vo.setAgentId(agentId);
        vo.setAgentStatus(AgentStatusEnum.BUSY.getCode());
        vo.setCallStartTime(LocalDateTime.now());
        log.info("坐席接单成功: agentId={}, orderId={}", agentId, orderId);
        return vo;
    }

    @Override
    @Transactional
    public AgentCompleteVO completeOrder(Long orderId, Long agentId, String manualSummary) {
        // 1. 更新工单：摘要 + 通话结束时间 + 状态办结 + AI 未解决
        WorkOrder order = workOrderMapper.selectById(orderId);
        if (order == null) {
            throw new BusinessException("工单不存在: " + orderId);
        }
        LambdaUpdateWrapper<WorkOrder> orderWrapper = new LambdaUpdateWrapper<>();
        orderWrapper.eq(WorkOrder::getOrderId, orderId)
                    .set(WorkOrder::getBizSummary, manualSummary)
                    .set(WorkOrder::getCallEndTime, LocalDateTime.now())
                    .set(WorkOrder::getOrderStatus, 2) // 已办结
                    .set(WorkOrder::getAiSolved, 0)
                    .set(WorkOrder::getUpdateTime, LocalDateTime.now());
        workOrderMapper.update(null, orderWrapper);

        // 2. 释放坐席为在线空闲
        LambdaUpdateWrapper<AgentInfo> agentWrapper = new LambdaUpdateWrapper<>();
        agentWrapper.eq(AgentInfo::getAgentId, agentId)
                    .set(AgentInfo::getAgentStatus, AgentStatusEnum.ONLINE.getCode());
        agentInfoMapper.update(null, agentWrapper);

        // 3. 更新 Redis
        redisTemplate.opsForValue().set(REDIS_KEY_PREFIX + agentId, AgentStatusEnum.ONLINE.getCode());

        AgentCompleteVO vo = new AgentCompleteVO();
        vo.setOrderId(orderId);
        vo.setAgentId(agentId);
        vo.setAgentStatus(AgentStatusEnum.ONLINE.getCode());
        vo.setBizSummary(manualSummary);
        vo.setCallEndTime(LocalDateTime.now());
        log.info("坐席办结成功: agentId={}, orderId={}", agentId, orderId);
        return vo;
    }
}
