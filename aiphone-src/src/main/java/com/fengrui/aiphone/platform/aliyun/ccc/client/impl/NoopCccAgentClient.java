package com.fengrui.aiphone.platform.aliyun.ccc.client.impl;

import com.fengrui.aiphone.platform.aliyun.ccc.client.CccAgentClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/**
 * CCC 坐席客户端空实现（Mock）。
 * <p>打印 Mock 日志，不执行真实 CCC 调用。</p>
 * <p>通过 {@code CccConfiguration#noopCccAgentClient()} 以
 * {@code @Bean @ConditionalOnMissingBean} 注册，当容器中不存在其他
 * {@link CccAgentClient} 实现时自动激活。下阶段实现真实 CccAgentClient
 * 并注册为 Bean 后，Noop 自动让位。</p>
 */
public class NoopCccAgentClient implements CccAgentClient {

    private static final Logger log = LoggerFactory.getLogger(NoopCccAgentClient.class);

    @Override
    public void signInGroup(Long agentId) {
        log.info("Mock CCC call: signInGroup(agentId={})", agentId);
    }

    @Override
    public void signOutGroup(Long agentId) {
        log.info("Mock CCC call: signOutGroup(agentId={})", agentId);
    }
}
