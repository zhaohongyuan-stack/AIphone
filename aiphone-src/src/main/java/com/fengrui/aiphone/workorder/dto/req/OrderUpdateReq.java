package com.fengrui.aiphone.workorder.dto.req;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 更新工单请求（PATCH 部分更新，所有字段非必填，有哪个更新哪个）。
 * <p>entCerdit 保留数据库笔误字段名（对齐数据库.md）。</p>
 */
@Data
public class OrderUpdateReq {

    private String entName;
    private String entAddress;
    private String entCerdit;       // 对齐数据库 ent_cerdit（原文档笔误）
    private String contactName;
    private String bizSummary;
    private Integer summaryConfirmed;
    private Integer orderType;
    private Long agentId;
    private Integer aiSolved;
    private String aiFailureNote;
    private Integer orderStatus;      // 工单状态（0-主动挂断 1-处理中 2-已办结 3-待回访 4-排队中 5-振铃中）
    private String phone;             // 来电号码
    private LocalDateTime callStartTime;  // 通话开始时间
    private LocalDateTime callEndTime;    // 通话结束时间
}
