package com.fengrui.aiphone.auth.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fengrui.aiphone.auth.dto.LoginRequest;
import com.fengrui.aiphone.auth.entity.AppUser;
import com.fengrui.aiphone.auth.mapper.AppUserMapper;
import com.fengrui.aiphone.auth.vo.AuthUserVO;
import com.fengrui.aiphone.auth.vo.LoginVO;
import com.fengrui.aiphone.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final AppUserMapper appUserMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenService jwtTokenService;

    public LoginVO login(LoginRequest request) {
        AppUser user = appUserMapper.selectOne(new LambdaQueryWrapper<AppUser>()
                .eq(AppUser::getUsername, request.username()));
        if (user == null || !Boolean.TRUE.equals(user.getEnabled())
                || !passwordEncoder.matches(request.password(), user.getPasswordHash())) {
            throw new BusinessException(401, "用户名或密码错误");
        }
        String token = jwtTokenService.createToken(user.getUserId(), user.getUsername(), user.getRole());
        return new LoginVO(token, "Bearer", jwtTokenService.expiresInSeconds(), toUserVO(user));
    }

    public AuthUserVO currentUser(String username) {
        AppUser user = appUserMapper.selectOne(new LambdaQueryWrapper<AppUser>()
                .eq(AppUser::getUsername, username));
        if (user == null || !Boolean.TRUE.equals(user.getEnabled())) {
            throw new BusinessException(401, "登录状态已失效");
        }
        return toUserVO(user);
    }

    private AuthUserVO toUserVO(AppUser user) {
        return new AuthUserVO(user.getUserId(), user.getUsername(), user.getDisplayName(), user.getRole());
    }
}
