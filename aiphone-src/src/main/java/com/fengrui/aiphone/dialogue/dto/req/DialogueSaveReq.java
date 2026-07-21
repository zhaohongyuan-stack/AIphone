package com.fengrui.aiphone.dialogue.dto.req;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

/**
 * 保存对话明细请求（Python 端调用：直接落库 dialogue_detail）。
 */
@Data
public class DialogueSaveReq {

    @NotNull(message = "orderId 不能为空")
    private Long orderId;

    @NotBlank(message = "content 不能为空")
    private String content;

    @NotBlank(message = "role 不能为空")
    private String role;  // AI / user / worker / ivr
}
