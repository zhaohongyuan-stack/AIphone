package com.fengrui.aiphone.common.enums;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * 坐席状态枚举（以数据库.md 注释为准，解决接口文档与数据库文档的冲突）。
 * 0-离线 1-正忙 2-在线空闲
 */
@Getter
@AllArgsConstructor
public enum AgentStatusEnum {

    OFFLINE(0, "离线"),
    BUSY(1, "正忙"),
    ONLINE(2, "在线空闲");

    private final int code;
    private final String desc;

    public static AgentStatusEnum of(int code) {
        for (AgentStatusEnum e : values()) {
            if (e.code == code) {
                return e;
            }
        }
        throw new IllegalArgumentException("未知坐席状态: " + code);
    }
}
