package com.fengrui.aiphone.workorder.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 工单详情响应（按接口文档(1).md 响应示例）。
 * <p>agentName 需 join agent_info 表获取。</p>
 */
@Data
public class OrderDetailVO {

    private Long orderId;
    private String phone;
    private String entName;
    private String entAddress;
    private String entCerdit;       // 对齐数据库 ent_cerdit
    private String contactName;
    private Integer orderType;
    private Integer orderStatus;
    private Long agentId;
    private String agentName;       // 来自 agent_info 表
    private String bizSummary;
    private Integer aiSolved;
    private String aiFailureNote;
    private LocalDateTime callStartTime;
    private LocalDateTime callEndTime;
    private LocalDateTime createdTime;
    private LocalDateTime updateTime;
    private Integer summaryConfirmed;
}
