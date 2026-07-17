package com.fengrui.aiphone.dialogue.event;

import lombok.Getter;
import org.springframework.context.ApplicationEvent;

import java.time.LocalDateTime;

/**
 * 对话消息事件（用于解耦 ASR 回调与 SSE 推送）。
 * <p>语音转写回调写入 dialogue_detail 后可发布此事件，SSE 监听推送。</p>
 */
@Getter
public class DialogueMessageEvent extends ApplicationEvent {

    private final Long orderId;
    private final Long diaId;
    private final String role;
    private final String content;
    private final LocalDateTime msgTime;

    public DialogueMessageEvent(Object source, Long orderId, Long diaId, String role, String content, LocalDateTime msgTime) {
        super(source);
        this.orderId = orderId;
        this.diaId = diaId;
        this.role = role;
        this.content = content;
        this.msgTime = msgTime;
    }
}
