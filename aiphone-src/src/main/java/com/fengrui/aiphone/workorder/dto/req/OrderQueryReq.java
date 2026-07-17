package com.fengrui.aiphone.workorder.dto.req;

import lombok.Data;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

/**
 * 工单分页查询请求（支持 status、agentId、时间范围、orderType 筛选）。
 */
@Data
public class OrderQueryReq {

    private Integer status;
    private Long agentId;

    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime startTime;

    @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss")
    private LocalDateTime endTime;

    private Integer orderType;

    private Integer page = 1;
    private Integer pageSize = 20;
}
