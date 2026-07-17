package com.fengrui.aiphone.workorder.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 创建工单响应。
 */
@Data
public class OrderCreateVO {

    private Long orderId;
    private Integer orderStatus;
    private LocalDateTime createdTime;
}
