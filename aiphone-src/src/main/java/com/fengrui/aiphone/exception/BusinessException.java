package com.fengrui.aiphone.exception;

import lombok.Getter;

/**
 * 业务异常，全局拦截后返回 code=500（或自定义 code）。
 */
@Getter
public class BusinessException extends RuntimeException {

    private final Integer code;

    public BusinessException(String message) {
        super(message);
        this.code = 500;
    }

    public BusinessException(Integer code, String message) {
        super(message);
        this.code = code;
    }
}
