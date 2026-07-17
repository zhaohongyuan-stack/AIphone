package com.fengrui.aiphone.platform.aliyun.ccc.config;

import jakarta.annotation.PostConstruct;
import lombok.Data;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

import java.time.Duration;

/**
 * 阿里云 CCC（云呼叫中心）模块配置属性。
 *
 * <p>作为整个 CCC 模块的「单一事实来源（Single Source of Truth）」，
 * 后续所有 CCC 相关组件（真实客户端、签名校验、回调接收）均从此类读取配置。</p>
 *
 * <h3>Fail-fast 校验策略</h3>
 * <p>当 {@link #enabled} = true 时，以下字段必填，缺失则应用启动失败
 * （{@link #validate()} 抛出 {@link IllegalStateException}，
 * 被 Spring 包装为 {@code BeanCreationException}，绝不带着残缺配置运行）：</p>
 * <ul>
 *   <li>{@link #instanceId}</li>
 *   <li>{@link #accessKeyId}</li>
 *   <li>{@link #accessKeySecret}</li>
 * </ul>
 *
 * <p>实现说明：Spring Boot 对 {@code @ConfigurationProperties} 的自动 JSR-303 校验
 * 只可靠支持字段级约束（如 {@code @NotEmpty}），对方法级约束（如 {@code @AssertTrue}）
 * 支持不稳定。因此条件必填校验通过 {@link PostConstruct} 手动实现，保证可靠触发。
 * {@link EnabledGroup} 接口仅作为文档标记与未来手动校验的扩展点保留。</p>
 *
 * <h3>音频流来源</h3>
 * <p>{@link #audioSourceType} 解决「音频从哪来」的模糊点：
 * 等 CCC 文档拿到后，改这个枚举值即可切换实现，无需改代码。</p>
 */
@Data
@Validated
@ConfigurationProperties(prefix = "aliyun.ccc")
public class CccProperties {

    private static final Logger log = LoggerFactory.getLogger(CccProperties.class);

    // ==================== 1. 基础开关 ====================

    /**
     * 总开关。
     * <p>true: 连接真实阿里云 CCC（需填下方凭证，启动时 Fail-fast 校验必填项）</p>
     * <p>false: 走本地 Noop 空实现（默认，适合开发测试）</p>
     */
    private Boolean enabled = false;

    // ==================== 2. 实例与凭证（enabled=true 时必填） ====================

    /**
     * 阿里云 CCC 实例 ID。在控制台「实例管理」中获取，格式如 {@code ccc-test}。
     * <p>当 {@link #enabled} = true 时必填，缺失则启动失败。</p>
     */
    private String instanceId;

    /**
     * 阿里云账号的 AccessKey ID（需具备 CCC 操作权限）。
     * <p>当 {@link #enabled} = true 时必填。建议通过环境变量 {@code ${CCC_AK_ID}} 注入。</p>
     */
    private String accessKeyId;

    /**
     * 阿里云账号的 AccessKey Secret（敏感信息）。
     * <p>当 {@link #enabled} = true 时必填。<b>强烈建议通过环境变量 {@code ${CCC_AK_SECRET}} 注入，禁止硬编码到代码仓库。</b></p>
     */
    private String accessKeySecret;

    // ==================== 3. 地域与端点 ====================

    /**
     * 服务地域。目前 CCC 开放地域主要有 {@code cn-shanghai} / {@code cn-beijing}。
     */
    private String regionId = "cn-shanghai";

    /**
     * API 网关地址。一般不填，SDK 会根据 {@link #regionId} 自动拼接；保留扩展能力。
     * <p>为 null 或空时，自动取 {@code ccc.{regionId}.aliyuncs.com}。</p>
     */
    private String apiEndpoint;

    // ==================== 4. 本地回调接收路径 ====================

    /**
     * 接收 CCC 回调的本地路径。若未来加网关前缀可在此统一修改。
     */
    private String callbackPath = "/api/aliyun/ccc/callback";

    // ==================== 5. 音频流来源（解决"音频从哪来"） ====================

    /**
     * 音频流来源类型。等 CCC 文档拿到后，改这个枚举值即可切换实现。
     * <ul>
     *   <li>{@code NONE}: 不接入音频（本阶段默认）</li>
     *   <li>{@code CALLBACK_BODY}: 回调请求体中直接携带音频（需文档确认）</li>
     *   <li>{@code WEBSOCKET_PULL}: 通过 WebSocket 主动拉取音频流（需额外实现）</li>
     * </ul>
     */
    private AudioSourceType audioSourceType = AudioSourceType.NONE;

    // ==================== 6. 网络超时 ====================

    /**
     * 网络超时配置。
     */
    private TimeoutConfig timeout = new TimeoutConfig();

    // ==================== 7. RocketMQ 事件订阅（联调阶段） ====================

    /**
     * RocketMQ 事件订阅配置。
     * <p>CCC 事件推送机制：CCC → RocketMQ Topic → 我方 Consumer 拉取。
     * 不支持 Webhook HTTP 回调，因此本地开发无需公网暴露。</p>
     */
    private MqConfig mq = new MqConfig();

    // ==================== Fail-fast 条件校验 ====================

    /**
     * 启动时校验：当 enabled=true 时必填项不能为空，缺失则抛异常阻止启动。
     * <p>通过 {@link PostConstruct} 在 Bean 初始化后立即触发，保证 Fail-fast。</p>
     */
    @PostConstruct
    public void validate() {
        if (!Boolean.TRUE.equals(enabled)) {
            log.info("CCC 模块未启用（aliyun.ccc.enabled=false），使用 Noop 空实现");
            return;
        }
        log.info("CCC 模块已启用（aliyun.ccc.enabled=true），开始校验必填配置...");
        if (isBlank(instanceId)) {
            throw new IllegalStateException(
                    "CCC instance-id 不能为空（aliyun.ccc.enabled=true 时必填，请在 application.yml 中配置 aliyun.ccc.instance-id）");
        }
        if (isBlank(accessKeyId)) {
            throw new IllegalStateException(
                    "CCC access-key-id 不能为空（aliyun.ccc.enabled=true 时必填，建议用环境变量 ${CCC_AK_ID} 注入）");
        }
        if (isBlank(accessKeySecret)) {
            throw new IllegalStateException(
                    "CCC access-key-secret 不能为空（aliyun.ccc.enabled=true 时必填，建议用环境变量 ${CCC_AK_SECRET} 注入）");
        }
        // MQ 配置校验：mq.enabled=true 时必填
        if (mq != null && Boolean.TRUE.equals(mq.getEnabled())) {
            if (isBlank(mq.getEndpoint())) {
                throw new IllegalStateException(
                        "CCC mq.endpoint 不能为空（aliyun.ccc.mq.enabled=true 时必填，RocketMQ 4.0 公网接入点）");
            }
            if (isBlank(mq.getTopic())) {
                throw new IllegalStateException(
                        "CCC mq.topic 不能为空（aliyun.ccc.mq.enabled=true 时必填）");
            }
            if (isBlank(mq.getConsumerGroup())) {
                throw new IllegalStateException(
                        "CCC mq.consumer-group 不能为空（aliyun.ccc.mq.enabled=true 时必填）");
            }
            // RocketMQ 5.x 公网访问必须设置实例用户名密码和 namespace（实例 ID）
            if (isBlank(mq.getUsername())) {
                throw new IllegalStateException(
                        "CCC mq.username 不能为空（RocketMQ 5.x 公网访问必须填写实例用户名）");
            }
            if (isBlank(mq.getPassword())) {
                throw new IllegalStateException(
                        "CCC mq.password 不能为空（RocketMQ 5.x 公网访问必须填写实例密码）");
            }
            if (isBlank(mq.getNamespace())) {
                throw new IllegalStateException(
                        "CCC mq.namespace 不能为空（RocketMQ 5.x 公网访问必须填写实例 ID，如 rmq-cn-xxx）");
            }
        }
        log.info("CCC 配置校验通过: instanceId={}, regionId={}, audioSourceType={}, mq.enabled={}",
                instanceId, regionId, audioSourceType, mq != null ? mq.getEnabled() : null);
    }

    private static boolean isBlank(String s) {
        return s == null || s.isBlank();
    }

    // ==================== 动态默认值 ====================

    /**
     * 获取 API 端点。未配置时自动按 {@code ccc.{regionId}.aliyuncs.com} 拼接。
     */
    public String getApiEndpoint() {
        if (apiEndpoint != null && !apiEndpoint.isBlank()) {
            return apiEndpoint;
        }
        String region = (regionId != null && !regionId.isBlank()) ? regionId : "cn-shanghai";
        return "ccc." + region + ".aliyuncs.com";
    }

    // ==================== 内部类与枚举 ====================

    /**
     * 网络超时配置（Duration 类型，支持 {@code 30s} / {@code 1m} 等格式）。
     */
    @Data
    public static class TimeoutConfig {
        /** 建立连接超时时间，默认 30 秒 */
        private Duration connect = Duration.ofSeconds(30);

        /** 读取数据超时时间，默认 30 秒 */
        private Duration read = Duration.ofSeconds(30);
    }

    /**
     * RocketMQ 事件订阅配置（RocketMQ 5.x 系列）。
     * <p>CCC 事件通过 RocketMQ 5.x 推送，我方使用 gRPC 协议 SDK（rocketmq-client-java 5.0.7）主动拉取。
     * 公网访问必须设置实例用户名、密码和 namespace（实例 ID）。</p>
     */
    @Data
    public static class MqConfig {
        /** 是否启用 MQ 消费者（联调阶段启用） */
        private Boolean enabled = false;

        /** RocketMQ 5.x 公网 gRPC 接入点（格式如 xxx.cn-beijing.rmq.aliyuncs.com:8080） */
        private String endpoint;

        /** RocketMQ 实例 ID（namespace，公网访问必填，如 rmq-cn-xxx） */
        private String namespace;

        /** 订阅的 Topic 名称（需与 CCC 控制台事件推送配置一致） */
        private String topic;

        /** 消费者 Group ID（需在 RocketMQ 控制台创建，类型=消费者） */
        private String consumerGroup;

        /** RocketMQ 实例用户名（公网访问必填，控制台 → 访问控制 → 智能身份识别） */
        private String username;

        /** RocketMQ 实例密码（公网访问必填） */
        private String password;

        /** 消费线程数，默认 20 */
        private Integer consumeThread = 20;
    }

    /**
     * 音频流来源枚举。
     */
    public enum AudioSourceType {
        /** 不接入音频（本阶段默认） */
        NONE,
        /** 回调请求体中直接携带音频（需文档确认） */
        CALLBACK_BODY,
        /** 通过 WebSocket 主动拉取音频流（需额外实现） */
        WEBSOCKET_PULL
    }

    /**
     * 分组校验接口（文档标记 + 未来手动校验扩展点）。
     * <p>当前条件必填校验通过 {@link #validate()} ({@link PostConstruct}) 实现。
     * 此接口保留供未来手动 {@code validator.validate(props, EnabledGroup.class)} 使用。</p>
     */
    public interface EnabledGroup {
    }
}
