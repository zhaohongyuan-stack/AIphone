package com.fengrui.aiphone.auth.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fengrui.aiphone.auth.entity.AppUser;
import com.fengrui.aiphone.auth.mapper.AppUserMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class AuthBootstrapService implements ApplicationRunner {

    private final AppUserMapper appUserMapper;
    private final PasswordEncoder passwordEncoder;
    private final String username;
    private final String password;
    private final String displayName;

    public AuthBootstrapService(
            AppUserMapper appUserMapper,
            PasswordEncoder passwordEncoder,
            @Value("${auth.bootstrap-username:admin}") String username,
            @Value("${auth.bootstrap-password}") String password,
            @Value("${auth.bootstrap-display-name:测试管理员}") String displayName) {
        this.appUserMapper = appUserMapper;
        this.passwordEncoder = passwordEncoder;
        this.username = username;
        this.password = password;
        this.displayName = displayName;
    }

    @Override
    public void run(ApplicationArguments args) {
        bootstrap();
    }

    public void bootstrap() {
        AppUser existing = appUserMapper.selectOne(new LambdaQueryWrapper<AppUser>()
                .eq(AppUser::getUsername, username));
        if (existing != null) {
            return;
        }
        AppUser user = new AppUser();
        user.setUsername(username);
        user.setPasswordHash(passwordEncoder.encode(password));
        user.setDisplayName(displayName);
        user.setRole("ADMIN");
        user.setEnabled(true);
        appUserMapper.insert(user);
    }
}
