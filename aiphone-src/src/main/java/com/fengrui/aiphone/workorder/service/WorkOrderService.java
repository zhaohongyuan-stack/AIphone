package com.fengrui.aiphone.workorder.service;

import com.fengrui.aiphone.workorder.dto.req.OrderCreateReq;
import com.fengrui.aiphone.workorder.dto.req.OrderQueryReq;
import com.fengrui.aiphone.workorder.dto.req.OrderStatusUpdateReq;
import com.fengrui.aiphone.workorder.dto.req.OrderUpdateReq;
import com.fengrui.aiphone.workorder.entity.WorkOrder;
import com.fengrui.aiphone.workorder.vo.OrderCreateVO;
import com.fengrui.aiphone.workorder.vo.OrderDetailVO;
import com.fengrui.aiphone.workorder.vo.OrderListVO;
import com.fengrui.aiphone.workorder.vo.OrderStatusUpdateVO;
import com.fengrui.aiphone.workorder.vo.OrderUpdateVO;
import com.fengrui.aiphone.workorder.vo.PageResult;
import com.fengrui.aiphone.workorder.vo.PhoneHistoryVO;

/**
 * 工单服务接口。
 */
public interface WorkOrderService {

    OrderCreateVO createOrder(OrderCreateReq req);

    /**
     * 便捷重载：CCC 接通事件（Established）创建工单。
     * <p>内部构造 {@link OrderCreateReq} 调用 {@link #createOrder(OrderCreateReq)}。</p>
     *
     * @param phone          主叫号码
     * @param conversationId CCC contactId（话务 ID）
     * @param instanceId     CCC 实例 ID
     * @return 创建结果（含 orderId，供后续事件使用）
     */
    OrderCreateVO createOrder(String phone, String conversationId, String instanceId);

    /**
     * 通过 conversationId（= CCC contactId）查找工单。
     * <p>用于 Established 事件幂等查找：Python 可能已在 IVR 阶段创建了工单。</p>
     *
     * @param conversationId CCC contactId
     * @return 工单实体，未找到返回 null
     */
    WorkOrder findByConversationId(String conversationId);

    /**
     * 便捷重载：CCC 挂机事件（Released）更新工单状态。
     * <p>内部调用 {@link #confirmOrder(Long, Integer)}。</p>
     *
     * @param orderId      工单 ID
     * @param orderStatus 目标状态（0-主动挂断 1-处理中 2-已办结 3-待回访 4-排队中 5-振铃中）
     */
    void updateStatus(Long orderId, Integer orderStatus);

    /**
     * 更新通话结束时间 + 工单状态（Released 事件用）。
     * <p>同时更新 call_end_time、order_status、update_time。</p>
     *
     * @param orderId 工单 ID
     * @param orderStatus 目标状态（通常 2-已办结 或 0-主动挂断）
     */
    void updateCallEndTime(Long orderId, Integer orderStatus);

    OrderDetailVO getOrderDetail(Long orderId);

    OrderUpdateVO updateOrder(Long orderId, OrderUpdateReq req);

    PageResult<OrderListVO> listOrders(OrderQueryReq req);

    PhoneHistoryVO listByPhone(String phone, Integer limit);

    OrderStatusUpdateVO confirmOrder(Long orderId, Integer orderStatus);

    /**
     * 工单流转推送（办结 + 设置 call_end_time）。
     * <p>Python 端调用：工单完结后流转到下游处理。</p>
     *
     * @param orderId 工单 ID
     * @return 更新结果
     */
    OrderStatusUpdateVO dispatchOrder(Long orderId);
}
