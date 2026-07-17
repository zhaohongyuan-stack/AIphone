package com.fengrui.aiphone.workorder.dto.req;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 工单状态变更请求（order_id 从 URL 路径获取）。
 */
@Data
public class OrderStatusUpdateReq {

    @NotNull(message = "orderStatus 不能为空")
    private Integer orderStatus;
}
