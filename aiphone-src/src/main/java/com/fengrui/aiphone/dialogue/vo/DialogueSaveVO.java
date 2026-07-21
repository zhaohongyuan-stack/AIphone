package com.fengrui.aiphone.dialogue.vo;

import lombok.Data;

import java.time.LocalDateTime;

/**
 * 保存对话明细返回值。
 */
@Data
public class DialogueSaveVO {
    private Long diaId;
    private LocalDateTime msgTime;
}
