package com.fengrui.aiphone.workorder.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 更新工单响应。
 */
@Data
public class OrderUpdateVO {

    private Long orderId;
    private LocalDateTime updateTime;
}
