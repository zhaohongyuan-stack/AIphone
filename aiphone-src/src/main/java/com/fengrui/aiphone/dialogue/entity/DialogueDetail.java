package com.fengrui.aiphone.dialogue.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 对话明细表实体。
 * <p>role 取值：AI / user / worker / ivr提示</p>
 * <p>msg_time 为毫秒精度（TIMESTAMP(3)）</p>
 */
@Data
@TableName("dialogue_detail")
public class DialogueDetail {

    @TableId(type = IdType.AUTO)
    private Long diaId;

    private Long orderId;
    private String content;
    private String role;
    private LocalDateTime msgTime;
}
