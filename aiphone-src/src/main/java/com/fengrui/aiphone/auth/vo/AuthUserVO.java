package com.fengrui.aiphone.auth.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class AuthUserVO {

    private Long userId;
    private String username;
    private String displayName;
    private String role;
}
