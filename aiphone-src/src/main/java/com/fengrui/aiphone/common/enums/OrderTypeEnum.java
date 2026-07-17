package com.fengrui.aiphone.common.enums;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 工单类型枚举（以数据库.md 注释为准）。
 * 0-转播 1-咨询 2-投诉 3-回访
 */
@Getter
@AllArgsConstructor
public enum OrderTypeEnum {

    TRANSFER(0, "转播"),
    CONSULT(1, "咨询"),
    COMPLAINT(2, "投诉"),
    CALLBACK(3, "回访");

    private final int code;
    private final String desc;

    public static OrderTypeEnum of(int code) {
        for (OrderTypeEnum e : values()) {
            if (e.code == code) {
                return e;
            }
        }
        throw new IllegalArgumentException("未知工单类型: " + code);
    }
}
