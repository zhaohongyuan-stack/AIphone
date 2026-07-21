package com.fengrui.aiphone.auth.controller;

import com.fengrui.aiphone.auth.dto.LoginRequest;
import com.fengrui.aiphone.auth.service.AuthService;
import com.fengrui.aiphone.auth.vo.AuthUserVO;
import com.fengrui.aiphone.auth.vo.LoginVO;
import com.fengrui.aiphone.common.Result;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/login")
    public Result<LoginVO> login(@Valid @RequestBody LoginRequest request) {
        return Result.success(authService.login(request));
    }

    @GetMapping("/me")
    public Result<AuthUserVO> me(Authentication authentication) {
        return Result.success(authService.currentUser(authentication.getName()));
    }

    @PostMapping("/logout")
    public Result<Void> logout() {
        return Result.success();
    }
}
