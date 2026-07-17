package com.fengrui.aiphone.platform.aliyun.ccc.callback;

import com.fengrui.aiphone.platform.aliyun.ccc.config.CccProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.util.Collections;
import java.util.Set;

/**
 * CCC 回调安全校验工具。
 *
 * <p>由于阿里云 CCC Webhook 回调<b>不支持签名校验</b>（UpdateSubscription API 无签名相关参数），
 * 采用以下替代安全措施：</p>
 * <ol>
 *   <li><b>实例 ID 校验</b>：校验请求体中的 {@code instanceId} 是否为自己的实例（必做）</li>
 *   <li><b>IP 白名单</b>：限制来源 IP 为阿里云 CCC 出口 IP（预留扩展点，当前不启用）</li>
 *   <li><b>URL Token</b>：可选在 Webhook URL 中带 Token 参数（预留扩展点，当前不启用）</li>
 * </ol>
 *
 * <p>生产环境建议：在 Nginx/网关层做 IP 白名单过滤，应用层做 instanceId 校验。</p>
 */
@Component
public class CccCallbackSecurityUtil {

    private static final Logger log = LoggerFactory.getLogger(CccCallbackSecurityUtil.class);

    @Autowired
    private CccProperties cccProperties;

    /**
     * 校验实例 ID 是否为我方配置的实例。
     *
     * <p>当 {@code aliyun.ccc.enabled=false} 时（开发测试），允许所有 instanceId 通过。
     * 当 {@code enabled=true} 时，必须与配置的 {@code instance-id} 完全匹配。</p>
     *
     * @param instanceId 回调请求中的 instanceId
     * @return true 合法，false 非法
     */
    public boolean validateInstanceId(String instanceId) {
        if (!Boolean.TRUE.equals(cccProperties.getEnabled())) {
            log.debug("CCC 未启用，跳过 instanceId 校验: {}", instanceId);
            return true;
        }
        String configured = cccProperties.getInstanceId();
        if (configured == null || configured.isBlank()) {
            log.warn("CCC 已启用但 instance-id 未配置，跳过校验");
            return true;
        }
        boolean valid = configured.equals(instanceId);
        if (!valid) {
            log.warn("instanceId 校验失败：期望={}, 实际={}", configured, instanceId);
        }
        return valid;
    }

    /**
     * IP 白名单校验（预留扩展点，当前不启用）。
     *
     * <p>生产环境启用时，从配置或数据库读取阿里云 CCC 出口 IP 列表进行校验。
     * 当前实现始终返回 true（未启用）。</p>
     *
     * @param clientIp 客户端 IP
     * @return true 合法，false 非法
     */
    public boolean validateIp(String clientIp) {
        // TODO: 生产环境启用 IP 白名单时，从配置读取 CCC 出口 IP 列表
        // Set<String> allowedIps = cccProperties.getAllowedIps();
        // return allowedIps.contains(clientIp);
        log.debug("IP 白名单未启用，跳过校验: {}", clientIp);
        return true;
    }

    /**
     * 获取允许的 IP 白名单（预留扩展点）。
     *
     * @return 允许的 IP 集合，当前返回空集（未启用）
     */
    public Set<String> getAllowedIps() {
        // TODO: 从配置读取阿里云 CCC 出口 IP 列表
        return Collections.emptySet();
    }
}
