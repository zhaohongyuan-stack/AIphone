package com.fengrui.aiphone.common.enums;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 工单状态枚举（以数据库.md 注释为准）。
 * 0-主动挂断 1-处理中 2-已办结 3-待回访 4-排队中 5-振铃中
 */
@Getter
@AllArgsConstructor
public enum OrderStatusEnum {

    HANG_UP(0, "主动挂断"),
    PROCESSING(1, "处理中"),
    DONE(2, "已办结"),
    CALLBACK(3, "待回访"),
    QUEUING(4, "排队中"),
    RINGING(5, "振铃中");

    private final int code;
    private final String desc;

    public static OrderStatusEnum of(int code) {
        for (OrderStatusEnum e : values()) {
            if (e.code == code) {
                return e;
            }
        }
        throw new IllegalArgumentException("未知工单状态: " + code);
    }
}
