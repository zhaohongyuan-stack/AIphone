package com.fengrui.aiphone.workorder.controller;

import com.fengrui.aiphone.common.Result;
import com.fengrui.aiphone.workorder.dto.req.OrderCreateReq;
import com.fengrui.aiphone.workorder.dto.req.OrderQueryReq;
import com.fengrui.aiphone.workorder.dto.req.OrderStatusUpdateReq;
import com.fengrui.aiphone.workorder.dto.req.OrderUpdateReq;
import com.fengrui.aiphone.workorder.service.WorkOrderService;
import com.fengrui.aiphone.workorder.vo.OrderCreateVO;
import com.fengrui.aiphone.workorder.vo.OrderDetailVO;
import com.fengrui.aiphone.workorder.vo.OrderListVO;
import com.fengrui.aiphone.workorder.vo.OrderStatusUpdateVO;
import com.fengrui.aiphone.workorder.vo.OrderUpdateVO;
import com.fengrui.aiphone.workorder.vo.PageResult;
import com.fengrui.aiphone.workorder.vo.PhoneHistoryVO;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

/**
 * 工单接口（严格对齐 docs/接口文档(1).md）。
 */
@RestController
@RequestMapping("/api/orders")
public class WorkOrderController {

    @Autowired
    private WorkOrderService workOrderService;

    /** 1. 创建工单（IVR 内调用） */
    @PostMapping
    public Result<OrderCreateVO> create(@Valid @RequestBody OrderCreateReq req) {
        return Result.success("工单创建成功", workOrderService.createOrder(req));
    }

    /** 2. 获取工单详情 */
    @GetMapping("/{order_id}")
    public Result<OrderDetailVO> detail(@PathVariable("order_id") Long orderId) {
        return Result.success(workOrderService.getOrderDetail(orderId));
    }

    /** 3. 更新工单（部分更新） */
    @PatchMapping("/{order_id}")
    public Result<OrderUpdateVO> update(@PathVariable("order_id") Long orderId,
                                        @RequestBody OrderUpdateReq req) {
        return Result.success("工单更新成功", workOrderService.updateOrder(orderId, req));
    }

    /** 4. 分页查询工单列表 */
    @GetMapping
    public Result<PageResult<OrderListVO>> list(OrderQueryReq req) {
        return Result.success(workOrderService.listOrders(req));
    }

    /** 5. 根据电话查历史工单 */
    @GetMapping("/by-phone")
    public Result<PhoneHistoryVO> byPhone(@RequestParam String phone,
                                           @RequestParam(required = false, defaultValue = "5") Integer limit) {
        return Result.success(workOrderService.listByPhone(phone, limit));
    }

    /** 6. 工单状态变更 */
    @PutMapping("/{order_id}/confirm")
    public Result<OrderStatusUpdateVO> confirm(@PathVariable("order_id") Long orderId,
                                               @Valid @RequestBody OrderStatusUpdateReq req) {
        return Result.success("状态更新成功", workOrderService.confirmOrder(orderId, req.getOrderStatus()));
    }
}
