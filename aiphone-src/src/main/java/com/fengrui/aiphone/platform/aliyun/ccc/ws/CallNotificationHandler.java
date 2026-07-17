package com.fengrui.aiphone.platform.aliyun.ccc.ws;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 来电通知 WebSocket Handler（支持坐席绑定 + 定向推送）。
 *
 * <p>端点：/ws/call
 *
 * <p>消息流向：
 * <ul>
 *   <li>前端→服务端：连接后发送 {"type":"BIND","cccAgentId":"agent001@instance"} 绑定坐席身份</li>
 *   <li>服务端→前端：广播 NEW_CALL（Ringing 时，通知所有坐席有新来电）</li>
 *   <li>服务端→前端：定向推送 ORDER_READY（Established 时，通知指定坐席工单就绪）</li>
 * </ul></p>
 *
 * <p>消息格式（JSON）：
 * <pre>
 * // 新来电（Ringing 广播）
 * {"type":"NEW_CALL","contactId":"job-xxx","caller":"13800138000",...}
 *
 * // 工单就绪（Established 定向推送）
 * {"type":"ORDER_READY","contactId":"job-xxx","orderId":17,"cccAgentId":"agent001@instance"}
 * </pre></p>
 */
@Component
public class CallNotificationHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(CallNotificationHandler.class);

    /** 全局已连接客户端集合（线程安全） */
    private final Set<WebSocketSession> sessions = ConcurrentHashMap.newKeySet();

    /** cccAgentId → WebSocketSession 映射（用于定向推送） */
    private final Map<String, WebSocketSession> agentSessionMap = new ConcurrentHashMap<>();

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessions.add(session);
        log.info("[WS] 客户端连接: id={}, 当前连接数={}", session.getId(), sessions.size());
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session);
        // 移除 agent 绑定
        agentSessionMap.entrySet().removeIf(e -> e.getValue().getId().equals(session.getId()));
        log.info("[WS] 客户端断开: id={}, status={}, 当前连接数={}", session.getId(), status, sessions.size());
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        try {
            Map<?, ?> msg = objectMapper.readValue(message.getPayload(), Map.class);
            String type = (String) msg.get("type");

            if ("BIND".equals(type)) {
                // 坐席绑定身份
                String cccAgentId = (String) msg.get("cccAgentId");
                if (cccAgentId != null && !cccAgentId.isBlank()) {
                    agentSessionMap.put(cccAgentId, session);
                    log.info("[WS] 坐席绑定: sessionId={}, cccAgentId={}", session.getId(), cccAgentId);

                    // 回复绑定成功
                    Map<String, Object> ack = new LinkedHashMap<>();
                    ack.put("type", "BIND_ACK");
                    ack.put("cccAgentId", cccAgentId);
                    ack.put("success", true);
                    sendMessage(session, ack);
                }
            } else if ("PING".equals(type)) {
                // 心跳
                Map<String, Object> pong = new LinkedHashMap<>();
                pong.put("type", "PONG");
                pong.put("timestamp", java.time.OffsetDateTime.now().toString());
                sendMessage(session, pong);
            }
        } catch (Exception e) {
            log.debug("[WS] 消息处理异常: id={}, payload={}, err={}",
                    session.getId(), message.getPayload(), e.getMessage());
        }
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        sessions.remove(session);
        agentSessionMap.entrySet().removeIf(e -> e.getValue().getId().equals(session.getId()));
        log.warn("[WS] 传输异常: id={}, err={}", session.getId(), exception.getMessage());
    }

    /**
     * 广播新来电通知到所有已连接客户端（Ringing 事件用）。
     *
     * @param contactId    话务ID
     * @param caller       主叫号码
     * @param callee       被叫号码
     * @param callType     呼叫类型
     * @param skillGroupId 技能组 ID
     */
    public void broadcastNewCall(String contactId, String caller, String callee, String callType, String skillGroupId) {
        if (sessions.isEmpty()) {
            log.debug("[WS] 无连接客户端，跳过广播");
            return;
        }

        Map<String, Object> message = new LinkedHashMap<>();
        message.put("type", "NEW_CALL");
        message.put("contactId", contactId);
        message.put("caller", caller);
        message.put("callee", callee);
        message.put("callType", callType);
        message.put("skillGroupId", skillGroupId);
        message.put("timestamp", java.time.OffsetDateTime.now().toString());

        broadcast(message, "NEW_CALL:" + contactId);
    }

    /**
     * 定向推送工单就绪通知到指定坐席（Established 事件用）。
     *
     * <p>前端收到此消息后，用 orderId 订阅 SSE 实时字幕。</p>
     *
     * @param contactId  话务ID
     * @param orderId    工单ID
     * @param cccAgentId CCC 坐席ID（用于定向推送）
     */
    public void broadcastOrderReady(String contactId, Long orderId, String cccAgentId) {
        Map<String, Object> message = new LinkedHashMap<>();
        message.put("type", "ORDER_READY");
        message.put("contactId", contactId);
        message.put("orderId", orderId);
        message.put("cccAgentId", cccAgentId);
        message.put("timestamp", java.time.OffsetDateTime.now().toString());

        if (cccAgentId != null && !cccAgentId.isBlank()) {
            // 定向推送给指定坐席
            WebSocketSession target = agentSessionMap.get(cccAgentId);
            if (target != null && target.isOpen()) {
                sendMessage(target, message);
                log.info("[WS] 工单就绪已定向推送: cccAgentId={}, orderId={}, contactId={}",
                        cccAgentId, orderId, contactId);
            } else {
                // 目标坐席未连接，降级为广播
                log.warn("[WS] 目标坐席未连接，降级广播: cccAgentId={}", cccAgentId);
                broadcast(message, "ORDER_READY:" + contactId);
            }
        } else {
            // 无 cccAgentId，广播
            broadcast(message, "ORDER_READY:" + contactId);
        }
    }

    /**
     * 广播消息到所有已连接客户端。
     */
    private void broadcast(Map<String, Object> message, String logTag) {
        try {
            String json = objectMapper.writeValueAsString(message);
            TextMessage textMessage = new TextMessage(json);
            int sent = 0;
            for (WebSocketSession s : sessions) {
                if (s.isOpen()) {
                    try {
                        synchronized (s) {
                            s.sendMessage(textMessage);
                        }
                        sent++;
                    } catch (IOException e) {
                        log.warn("[WS] 广播失败: id={}, err={}", s.getId(), e.getMessage());
                        sessions.remove(s);
                    }
                }
            }
            log.info("[WS] 广播完成: tag={}, 发送 {} 个客户端", logTag, sent);
        } catch (Exception e) {
            log.error("[WS] 广播序列化失败: {}", e.getMessage(), e);
        }
    }

    /**
     * 发送消息到单个会话。
     */
    private void sendMessage(WebSocketSession session, Map<String, Object> message) {
        try {
            String json = objectMapper.writeValueAsString(message);
            synchronized (session) {
                session.sendMessage(new TextMessage(json));
            }
        } catch (IOException e) {
            log.warn("[WS] 发送失败: id={}, err={}", session.getId(), e.getMessage());
        }
    }

    /**
     * 当前已连接客户端数（用于测试）。
     */
    public int connectedCount() {
        return sessions.size();
    }

    /**
     * 获取所有会话 ID（用于测试）。
     */
    public List<String> sessionIds() {
        return sessions.stream().map(WebSocketSession::getId).toList();
    }

    /**
     * 获取已绑定坐席数（用于测试）。
     */
    public int boundAgentCount() {
        return agentSessionMap.size();
    }
}
