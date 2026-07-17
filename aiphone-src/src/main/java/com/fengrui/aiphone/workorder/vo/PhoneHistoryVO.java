package com.fengrui.aiphone.workorder.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 根据电话查历史工单响应。
 */
@Data
public class PhoneHistoryVO {

    private String phone;
    private Integer total;
    private List<PhoneHistoryItem> list;

    /**
     * 历史工单列表项。
     */
    @Data
    public static class PhoneHistoryItem {
        private Long orderId;
        private Integer orderType;
        private String bizSummary;
        private Integer orderStatus;
        private LocalDateTime callStartTime;
    }
}
