package com.fengrui.aiphone.workorder.dto.req;

import lombok.Data;

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
}
