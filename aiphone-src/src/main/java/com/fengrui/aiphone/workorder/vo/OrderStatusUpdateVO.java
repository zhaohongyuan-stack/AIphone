package com.fengrui.aiphone.workorder.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 工单状态变更响应。
 */
@Data
public class OrderStatusUpdateVO {

    private Long orderId;
    private Integer orderStatus;
    private LocalDateTime updateTime;
}
