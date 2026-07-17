package com.fengrui.aiphone.config;

import com.fengrui.aiphone.platform.aliyun.ccc.ws.CallNotificationHandler;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * WebSocket 配置：注册来电通知端点。
 * <p>端点：ws://host:8080/ws/call
 * <p>用途：Ringing 事件时向所有连接的坐席前端推送新来电通知。</p>
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    @Autowired
    private CallNotificationHandler callNotificationHandler;

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(callNotificationHandler, "/ws/call")
                .setAllowedOrigins("*");
    }
}
