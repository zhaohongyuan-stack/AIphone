package com.fengrui.aiphone.platform.aliyun.ccc.client;

/**
 * 阿里云 CCC 坐席客户端接口（扩展点）。
 * <p>当前为 NoopCccAgentClient 空实现，下阶段对接真实 CCC 后用
 * @ConditionalOnProperty 自动切换。</p>
 */
public interface CccAgentClient {

    /**
     * 坐席签入技能组（上线）。
     */
    void signInGroup(Long agentId);

    /**
     * 坐席签出技能组（下线）。
     */
    void signOutGroup(Long agentId);
}
