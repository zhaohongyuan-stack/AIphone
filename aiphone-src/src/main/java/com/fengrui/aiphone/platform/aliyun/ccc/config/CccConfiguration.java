package com.fengrui.aiphone.platform.aliyun.ccc.config;

import com.fengrui.aiphone.platform.aliyun.ccc.client.CccAgentClient;
import com.fengrui.aiphone.platform.aliyun.ccc.client.impl.NoopCccAgentClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * CCC 模块配置注册类。
 * <p>通过 {@link EnableConfigurationProperties} 注册 {@link CccProperties}，
 * 确保 Spring Boot 走标准 {@code @ConfigurationProperties} 绑定路径。</p>
 *
 * <p>同时以 {@code @Bean @ConditionalOnMissingBean} 注册 {@link NoopCccAgentClient}
 * 作为 CCC 客户端的兜底空实现：当容器中不存在其他 {@link CccAgentClient} 实现时自动激活，
 * 未来实现真实客户端后自动让位。</p>
 */
@Configuration
@EnableConfigurationProperties(CccProperties.class)
public class CccConfiguration {

    @Bean
    @ConditionalOnMissingBean(CccAgentClient.class)
    public CccAgentClient noopCccAgentClient() {
        return new NoopCccAgentClient();
    }
}
