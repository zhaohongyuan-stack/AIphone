package com.fengrui.aiphone.auth.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class LoginVO {

    private String accessToken;
    private String tokenType;
    private Long expiresIn;
    private AuthUserVO user;
}
