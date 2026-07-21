package com.fengrui.aiphone.workorder.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 主工单表实体（严格对齐数据库.md，保留 ent_cerdit 笔误字段名）。
 */
@Data
@TableName("work_order")
public class WorkOrder {

    @TableId(type = IdType.AUTO)
    private Long orderId;

    private String conversationId;
    private String instanceId;
    private String entName;
    private String entAddress;
    private String entCerdit;       // 保留原文档笔误字段名
    private String phone;
    private String contactName;
    private Integer orderType;
    private Integer orderStatus;
    private Long agentId;
    private LocalDateTime createdTime;
    private LocalDateTime updateTime;
    private LocalDateTime callStartTime;
    private LocalDateTime callEndTime;
    private String bizSummary;
    private String aiFailureNote;
    private Integer aiSolved;
    private Integer summaryConfirmed;
}
