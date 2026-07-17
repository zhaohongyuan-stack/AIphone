package com.fengrui.aiphone.workorder.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 工单列表项（手机号已脱敏）。
 */
@Data
public class OrderListVO {

    private Long orderId;
    private String phone;           // 脱敏后：138****8000
    private String contactName;
    private Integer orderType;
    private Integer orderStatus;
    private String agentName;       // 来自 agent_info 表
    private String bizSummary;
    private LocalDateTime callStartTime;
    private LocalDateTime createdTime;
}
