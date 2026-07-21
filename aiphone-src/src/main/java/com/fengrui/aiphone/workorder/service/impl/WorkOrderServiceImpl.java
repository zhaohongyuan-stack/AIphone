package com.fengrui.aiphone.workorder.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fengrui.aiphone.agent.entity.AgentInfo;
import com.fengrui.aiphone.agent.mapper.AgentInfoMapper;
import com.fengrui.aiphone.common.enums.OrderStatusEnum;
import com.fengrui.aiphone.common.enums.OrderTypeEnum;
import com.fengrui.aiphone.exception.BusinessException;
import com.fengrui.aiphone.workorder.dto.req.OrderCreateReq;
import com.fengrui.aiphone.workorder.dto.req.OrderQueryReq;
import com.fengrui.aiphone.workorder.dto.req.OrderUpdateReq;
import com.fengrui.aiphone.workorder.entity.WorkOrder;
import com.fengrui.aiphone.workorder.mapper.WorkOrderMapper;
import com.fengrui.aiphone.workorder.service.WorkOrderService;
import com.fengrui.aiphone.workorder.vo.OrderCreateVO;
import com.fengrui.aiphone.workorder.vo.OrderDetailVO;
import com.fengrui.aiphone.workorder.vo.OrderListVO;
import com.fengrui.aiphone.workorder.vo.OrderStatusUpdateVO;
import com.fengrui.aiphone.workorder.vo.OrderUpdateVO;
import com.fengrui.aiphone.workorder.vo.PageResult;
import com.fengrui.aiphone.workorder.vo.PhoneHistoryVO;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

/**
 * 工单服务实现。
 * <p>使用 MyBatis-Plus Page 分页，PATCH 用 LambdaUpdateWrapper 只更新非空字段。</p>
 */
@Service
public class WorkOrderServiceImpl implements WorkOrderService {

    @Autowired
    private WorkOrderMapper workOrderMapper;

    @Autowired
    private AgentInfoMapper agentInfoMapper;

    @Override
    @Transactional
    public OrderCreateVO createOrder(OrderCreateReq req) {
        WorkOrder order = new WorkOrder();
        order.setPhone(req.getPhone());
        order.setConversationId(req.getConversationId());
        order.setInstanceId(req.getInstanceId());
        order.setOrderType(OrderTypeEnum.CONSULT.getCode());        // 默认咨询
        order.setOrderStatus(OrderStatusEnum.PROCESSING.getCode()); // 默认处理中
        order.setCallStartTime(LocalDateTime.now());              // IVR 开始即通话开始
        order.setCreatedTime(LocalDateTime.now());                // 显式赋值，兼容旧表无 DEFAULT
        order.setUpdateTime(LocalDateTime.now());
        order.setSummaryConfirmed(0);
        order.setAiSolved(0);
        workOrderMapper.insert(order);

        OrderCreateVO vo = new OrderCreateVO();
        vo.setOrderId(order.getOrderId());
        vo.setOrderStatus(order.getOrderStatus());
        vo.setCreatedTime(order.getCreatedTime());
        return vo;
    }

    @Override
    @Transactional
    public OrderCreateVO createOrder(String phone, String conversationId, String instanceId) {
        // phone 为空时给默认值，避免违反数据库 NOT NULL 约束（联调阶段可能无主叫号码）
        OrderCreateReq req = new OrderCreateReq();
        req.setPhone(phone == null || phone.isBlank() ? "unknown" : phone);
        req.setConversationId(conversationId);
        req.setInstanceId(instanceId);
        return createOrder(req);
    }

    @Override
    @Transactional
    public void updateStatus(Long orderId, Integer orderStatus) {
        confirmOrder(orderId, orderStatus);
    }

    @Override
    @Transactional
    public void updateCallEndTime(Long orderId, Integer orderStatus) {
        WorkOrder order = workOrderMapper.selectById(orderId);
        if (order == null) {
            throw new BusinessException("工单不存在: " + orderId);
        }
        OrderStatusEnum.of(orderStatus); // 校验枚举合法性
        LambdaUpdateWrapper<WorkOrder> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(WorkOrder::getOrderId, orderId)
               .set(WorkOrder::getOrderStatus, orderStatus)
               .set(WorkOrder::getCallEndTime, LocalDateTime.now())
               .set(WorkOrder::getUpdateTime, LocalDateTime.now());
        workOrderMapper.update(null, wrapper);
    }

    @Override
    public WorkOrder findByConversationId(String conversationId) {
        if (conversationId == null || conversationId.isBlank()) {
            return null;
        }
        LambdaQueryWrapper<WorkOrder> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(WorkOrder::getConversationId, conversationId).last("LIMIT 1");
        return workOrderMapper.selectOne(wrapper);
    }

    @Override
    public OrderDetailVO getOrderDetail(Long orderId) {
        WorkOrder order = workOrderMapper.selectById(orderId);
        if (order == null) {
            throw new BusinessException("工单不存在: " + orderId);
        }
        OrderDetailVO vo = new OrderDetailVO();
        BeanUtils.copyProperties(order, vo);
        // 查 agent_name
        if (order.getAgentId() != null) {
            AgentInfo agent = agentInfoMapper.selectById(order.getAgentId());
            if (agent != null) {
                vo.setAgentName(agent.getAgentName());
            }
        }
        return vo;
    }

    @Override
    @Transactional
    public OrderUpdateVO updateOrder(Long orderId, OrderUpdateReq req) {
        WorkOrder order = workOrderMapper.selectById(orderId);
        if (order == null) {
            throw new BusinessException("工单不存在: " + orderId);
        }
        LambdaUpdateWrapper<WorkOrder> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(WorkOrder::getOrderId, orderId);
        // 仅更新非空字段
        if (req.getEntName() != null) wrapper.set(WorkOrder::getEntName, req.getEntName());
        if (req.getEntAddress() != null) wrapper.set(WorkOrder::getEntAddress, req.getEntAddress());
        if (req.getEntCerdit() != null) wrapper.set(WorkOrder::getEntCerdit, req.getEntCerdit());
        if (req.getContactName() != null) wrapper.set(WorkOrder::getContactName, req.getContactName());
        if (req.getBizSummary() != null) wrapper.set(WorkOrder::getBizSummary, req.getBizSummary());
        if (req.getSummaryConfirmed() != null) wrapper.set(WorkOrder::getSummaryConfirmed, req.getSummaryConfirmed());
        if (req.getOrderType() != null) wrapper.set(WorkOrder::getOrderType, req.getOrderType());
        if (req.getAgentId() != null) wrapper.set(WorkOrder::getAgentId, req.getAgentId());
        if (req.getAiSolved() != null) wrapper.set(WorkOrder::getAiSolved, req.getAiSolved());
        if (req.getAiFailureNote() != null) wrapper.set(WorkOrder::getAiFailureNote, req.getAiFailureNote());
        if (req.getOrderStatus() != null) wrapper.set(WorkOrder::getOrderStatus, req.getOrderStatus());
        if (req.getPhone() != null) wrapper.set(WorkOrder::getPhone, req.getPhone());
        if (req.getCallStartTime() != null) wrapper.set(WorkOrder::getCallStartTime, req.getCallStartTime());
        if (req.getCallEndTime() != null) wrapper.set(WorkOrder::getCallEndTime, req.getCallEndTime());
        wrapper.set(WorkOrder::getUpdateTime, LocalDateTime.now());
        workOrderMapper.update(null, wrapper);

        OrderUpdateVO vo = new OrderUpdateVO();
        vo.setOrderId(orderId);
        vo.setUpdateTime(LocalDateTime.now());
        return vo;
    }

    @Override
    public PageResult<OrderListVO> listOrders(OrderQueryReq req) {
        Page<WorkOrder> page = new Page<>(req.getPage(), req.getPageSize());
        LambdaQueryWrapper<WorkOrder> wrapper = new LambdaQueryWrapper<>();
        if (req.getStatus() != null) wrapper.eq(WorkOrder::getOrderStatus, req.getStatus());
        if (req.getAgentId() != null) wrapper.eq(WorkOrder::getAgentId, req.getAgentId());
        if (req.getOrderType() != null) wrapper.eq(WorkOrder::getOrderType, req.getOrderType());
        if (req.getStartTime() != null) wrapper.ge(WorkOrder::getCallStartTime, req.getStartTime());
        if (req.getEndTime() != null) wrapper.le(WorkOrder::getCallStartTime, req.getEndTime());
        wrapper.orderByDesc(WorkOrder::getCreatedTime);

        Page<WorkOrder> result = workOrderMapper.selectPage(page, wrapper);

        List<OrderListVO> list = result.getRecords().stream().map(o -> {
            OrderListVO vo = new OrderListVO();
            vo.setOrderId(o.getOrderId());
            vo.setPhone(maskPhone(o.getPhone()));
            vo.setContactName(o.getContactName());
            vo.setOrderType(o.getOrderType());
            vo.setOrderStatus(o.getOrderStatus());
            vo.setBizSummary(o.getBizSummary());
            vo.setCallStartTime(o.getCallStartTime());
            vo.setCreatedTime(o.getCreatedTime());
            // 查 agent_name
            if (o.getAgentId() != null) {
                AgentInfo agent = agentInfoMapper.selectById(o.getAgentId());
                if (agent != null) vo.setAgentName(agent.getAgentName());
            }
            return vo;
        }).collect(Collectors.toList());

        return PageResult.of(result.getTotal(), req.getPage(), req.getPageSize(), list);
    }

    @Override
    public PhoneHistoryVO listByPhone(String phone, Integer limit) {
        LambdaQueryWrapper<WorkOrder> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(WorkOrder::getPhone, phone)
               .orderByDesc(WorkOrder::getCallStartTime);
        if (limit != null && limit > 0) {
            wrapper.last("LIMIT " + limit);
        }
        List<WorkOrder> orders = workOrderMapper.selectList(wrapper);

        PhoneHistoryVO vo = new PhoneHistoryVO();
        vo.setPhone(phone);
        vo.setTotal(orders.size());
        List<PhoneHistoryVO.PhoneHistoryItem> items = orders.stream().map(o -> {
            PhoneHistoryVO.PhoneHistoryItem item = new PhoneHistoryVO.PhoneHistoryItem();
            item.setOrderId(o.getOrderId());
            item.setOrderType(o.getOrderType());
            item.setBizSummary(o.getBizSummary());
            item.setOrderStatus(o.getOrderStatus());
            item.setCallStartTime(o.getCallStartTime());
            return item;
        }).collect(Collectors.toList());
        vo.setList(items);
        return vo;
    }

    @Override
    @Transactional
    public OrderStatusUpdateVO confirmOrder(Long orderId, Integer orderStatus) {
        WorkOrder order = workOrderMapper.selectById(orderId);
        if (order == null) {
            throw new BusinessException("工单不存在: " + orderId);
        }
        OrderStatusEnum.of(orderStatus); // 校验枚举合法性
        LambdaUpdateWrapper<WorkOrder> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(WorkOrder::getOrderId, orderId)
               .set(WorkOrder::getOrderStatus, orderStatus)
               .set(WorkOrder::getUpdateTime, LocalDateTime.now());
        workOrderMapper.update(null, wrapper);

        OrderStatusUpdateVO vo = new OrderStatusUpdateVO();
        vo.setOrderId(orderId);
        vo.setOrderStatus(orderStatus);
        vo.setUpdateTime(LocalDateTime.now());
        return vo;
    }

    @Override
    @Transactional
    public OrderStatusUpdateVO dispatchOrder(Long orderId) {
        WorkOrder order = workOrderMapper.selectById(orderId);
        if (order == null) {
            throw new BusinessException("工单不存在: " + orderId);
        }
        LambdaUpdateWrapper<WorkOrder> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(WorkOrder::getOrderId, orderId)
               .set(WorkOrder::getOrderStatus, OrderStatusEnum.DONE.getCode())
               .set(WorkOrder::getCallEndTime, LocalDateTime.now())
               .set(WorkOrder::getUpdateTime, LocalDateTime.now());
        workOrderMapper.update(null, wrapper);

        OrderStatusUpdateVO vo = new OrderStatusUpdateVO();
        vo.setOrderId(orderId);
        vo.setOrderStatus(OrderStatusEnum.DONE.getCode());
        vo.setUpdateTime(LocalDateTime.now());
        return vo;
    }

    /**
     * 手机号脱敏：13800138000 -> 138****8000
     */
    private String maskPhone(String phone) {
        if (phone == null || phone.length() < 7) {
            return phone;
        }
        return phone.substring(0, 3) + "****" + phone.substring(phone.length() - 4);
    }
}
