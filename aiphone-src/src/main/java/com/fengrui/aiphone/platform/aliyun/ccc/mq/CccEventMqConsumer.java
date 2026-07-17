package com.fengrui.aiphone.platform.aliyun.ccc.mq;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fengrui.aiphone.platform.aliyun.ccc.callback.CccCallbackService;
import com.fengrui.aiphone.platform.aliyun.ccc.callback.dto.*;
import com.fengrui.aiphone.platform.aliyun.ccc.config.CccProperties;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.ClientException;
import org.apache.rocketmq.client.apis.ClientServiceProvider;
import org.apache.rocketmq.client.apis.SessionCredentialsProvider;
import org.apache.rocketmq.client.apis.StaticSessionCredentialsProvider;
import org.apache.rocketmq.client.apis.consumer.ConsumeResult;
import org.apache.rocketmq.client.apis.consumer.FilterExpression;
import org.apache.rocketmq.client.apis.consumer.FilterExpressionType;
import org.apache.rocketmq.client.apis.consumer.PushConsumer;
import org.apache.rocketmq.client.apis.message.MessageView;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.Collections;

/**
 * RocketMQ 5.x 消费者：订阅 CCC 事件 Topic，解析后分发到 {@link CccCallbackService}。
 *
 * <p>使用 Apache RocketMQ 5.x gRPC 协议 SDK（rocketmq-client-java 5.0.7）。
 * CCC 事件推送机制：CCC 实例 → RocketMQ 5.x Topic → 我方 PushConsumer 拉取。</p>
 *
 * <h3>公网访问要求</h3>
 * <ul>
 *   <li>必须设置实例用户名密码（{@code username}/{@code password}）</li>
 *   <li>必须设置 namespace（实例 ID，如 {@code rmq-cn-xxx}）</li>
 *   <li>接入点格式：{@code rmq-cn-xxx.{regionId}.rmq.aliyuncs.com:8080}</li>
 * </ul>
 *
 * <h3>消息流转路径</h3>
 * <pre>
 * CCC 事件 → RocketMQ 5.x Topic → PushConsumer.messageListener →
 *   解析 JSON → 根据 eventType 分发 → CccCallbackService.handleXxx()
 *     → WorkOrderService / DialogueService / AgentInfoService
 *     → DB + Redis + SSE 推送
 * </pre>
 *
 * <h3>启用条件</h3>
 * <ul>
 *   <li>{@code aliyun.ccc.mq.enabled=true}</li>
 *   <li>{@code aliyun.ccc.enabled=true}（在 PostConstruct 中二次校验）</li>
 * </ul>
 */
@Component
@ConditionalOnProperty(prefix = "aliyun.ccc.mq", name = "enabled", havingValue = "true")
public class CccEventMqConsumer {

    private static final Logger log = LoggerFactory.getLogger(CccEventMqConsumer.class);

    @Autowired
    private CccProperties cccProperties;

    @Autowired
    private CccCallbackService cccCallbackService;

    @Autowired
    private ObjectMapper objectMapper;

    private PushConsumer pushConsumer;

    /**
     * 启动 RocketMQ 5.x PushConsumer。
     *
     * <p>在 Bean 初始化后自动触发。从 {@link CccProperties} 读取 MQ 配置，
     * 使用 gRPC 协议创建 PushConsumer 并订阅 CCC 事件 Topic。</p>
     */
    @PostConstruct
    public void start() {
        // 二次校验：CCC 总开关必须为 true
        if (!Boolean.TRUE.equals(cccProperties.getEnabled())) {
            log.info("[MQ] CCC 模块未启用（aliyun.ccc.enabled=false），跳过 MQ 消费者启动");
            return;
        }

        CccProperties.MqConfig mq = cccProperties.getMq();
        if (mq == null) {
            log.warn("[MQ] MQ 配置为空，跳过启动");
            return;
        }

        log.info("[MQ] 开始启动 CCC 事件消费者（RocketMQ 5.x gRPC）: endpoint={}, namespace={}, topic={}, group={}",
                mq.getEndpoint(), mq.getNamespace(), mq.getTopic(), mq.getConsumerGroup());

        try {
            // 1. 构建凭证提供者（实例用户名密码，公网访问必填）
            SessionCredentialsProvider credentialsProvider =
                    new StaticSessionCredentialsProvider(mq.getUsername(), mq.getPassword());

            // 2. 构建客户端配置（接入点 + namespace + 凭证）
            ClientConfiguration clientConfiguration = ClientConfiguration.newBuilder()
                    .setEndpoints(mq.getEndpoint())
                    .setNamespace(mq.getNamespace())
                    .setCredentialProvider(credentialsProvider)
                    .build();

            // 3. 构建订阅过滤表达式（tag=* 表示接收所有 tag）
            FilterExpression filterExpression = new FilterExpression("*", FilterExpressionType.TAG);

            // 4. 获取 SDK 提供者
            ClientServiceProvider provider = ClientServiceProvider.loadService();

            // 5. 创建 PushConsumer 并设置消息监听器
            pushConsumer = provider.newPushConsumerBuilder()
                    .setClientConfiguration(clientConfiguration)
                    .setConsumerGroup(mq.getConsumerGroup())
                    .setSubscriptionExpressions(Collections.singletonMap(mq.getTopic(), filterExpression))
                    .setMessageListener(this::handleMessage)
                    .build();

            log.info("[MQ] CCC 事件消费者已启动: endpoint={}, topic={}, group={}",
                    mq.getEndpoint(), mq.getTopic(), mq.getConsumerGroup());
        } catch (ClientException e) {
            log.error("[MQ] CCC 事件消费者启动失败: {}", e.getMessage(), e);
            throw new RuntimeException("RocketMQ 消费者启动失败", e);
        }
    }

    /**
     * 处理 RocketMQ 消息（PushConsumer 回调）。
     *
     * <p>解析消息体为 JSON，提取 eventType，分发到 {@link CccCallbackService} 对应方法。
     * 处理成功返回 {@link ConsumeResult#SUCCESS}，异常返回 {@link ConsumeResult#FAILURE}
     * 触发 RocketMQ 重试。</p>
     *
     * @param messageView 消息视图
     * @return 消费结果
     */
    private ConsumeResult handleMessage(MessageView messageView) {
        String msgId = messageView.getMessageId().toString();
        String topic = messageView.getTopic();

        // 读取消息体
        String body;
        try {
            byte[] bytes = new byte[messageView.getBody().remaining()];
            messageView.getBody().get(bytes);
            body = new String(bytes, StandardCharsets.UTF_8);
        } catch (Exception e) {
            log.error("[MQ] 消息体读取失败: msgId={}, topic={}", msgId, topic, e);
            return ConsumeResult.SUCCESS; // 读取失败的消息直接丢弃
        }

        // 提取 eventType
        String eventType;
        try {
            CccCallbackRequest base = objectMapper.readValue(body, CccCallbackRequest.class);
            eventType = base.getEventType();
        } catch (Exception e) {
            log.error("[MQ] JSON 解析失败: msgId={}, body={}", msgId, body, e);
            return ConsumeResult.SUCCESS; // 无法解析的消息直接丢弃
        }

        log.info("[MQ] 收到 CCC 事件: topic={}, msgId={}, eventType={}", topic, msgId, eventType);

        try {
            dispatchEvent(eventType, body);
            log.info("[MQ] 事件处理成功: msgId={}, eventType={}", msgId, eventType);
            return ConsumeResult.SUCCESS;
        } catch (Exception e) {
            log.error("[MQ] 事件处理失败（将重试）: msgId={}, eventType={}", msgId, eventType, e);
            return ConsumeResult.FAILURE;
        }
    }

    /**
     * 根据 eventType 分发到 {@link CccCallbackService} 对应方法。
     *
     * @param eventType 事件类型字符串
     * @param body      原始 JSON 字符串
     * @throws Exception 解析或处理异常
     */
    private void dispatchEvent(String eventType, String body) throws Exception {
        if (eventType == null) {
            log.warn("[MQ] eventType 为空: body={}", body);
            return;
        }
        switch (eventType) {
            case "Ringing":
                RingingEventData ringing = objectMapper.readValue(body, RingingEventData.class);
                cccCallbackService.handleRinging(ringing);
                break;
            case "Enqueue":
                CccCallEventData enqueue = objectMapper.readValue(body, CccCallEventData.class);
                cccCallbackService.handleEnqueue(enqueue);
                break;
            case "AssignAgent":
                AssignAgentEventData assignAgent = objectMapper.readValue(body, AssignAgentEventData.class);
                cccCallbackService.handleAssignAgent(assignAgent);
                break;
            case "Abandoned":
                AbandonedEventData abandoned = objectMapper.readValue(body, AbandonedEventData.class);
                cccCallbackService.handleAbandoned(abandoned);
                break;
            case "Established":
                EstablishedEventData established = objectMapper.readValue(body, EstablishedEventData.class);
                cccCallbackService.handleEstablished(established);
                break;
            case "Released":
                ReleasedEventData released = objectMapper.readValue(body, ReleasedEventData.class);
                cccCallbackService.handleReleased(released);
                break;
            case "RecordingReady":
                RecordingReadyEventData recording = objectMapper.readValue(body, RecordingReadyEventData.class);
                cccCallbackService.handleRecordingReady(recording);
                break;
            case "TextStream":
                TextStreamEventData textStream = objectMapper.readValue(body, TextStreamEventData.class);
                cccCallbackService.handleTextStream(textStream);
                break;
            case "AgentCheckIn":
            case "AgentReady":
            case "AgentDialing":
            case "AgentRinging":
            case "AgentTalk":
            case "AgentRelease":
            case "AgentBreak":
            case "AgentCheckOut":
            case "AgentRingingTimeout":
                CccAgentEventData agentEvent = objectMapper.readValue(body, CccAgentEventData.class);
                cccCallbackService.handleAgentEvent(eventType, agentEvent);
                break;
            default:
                cccCallbackService.handleUnknownEvent(eventType, body);
                break;
        }
    }

    /**
     * 关闭 PushConsumer。
     */
    @PreDestroy
    public void shutdown() {
        if (pushConsumer != null) {
            try {
                pushConsumer.close();
                log.info("[MQ] CCC 事件消费者已关闭");
            } catch (Exception e) {
                log.warn("[MQ] 关闭消费者异常: {}", e.getMessage());
            }
        }
    }
}
