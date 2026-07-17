package com.fengrui.aiphone.workorder.dto.req;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;

/**
 * 创建工单请求（IVR 内调用，只传 phone / conversationId / instanceId）。
 */
@Data
public class OrderCreateReq {

    @NotBlank(message = "phone 不能为空")
    private String phone;

    @NotBlank(message = "conversationId 不能为空")
    private String conversationId;

    @NotBlank(message = "instanceId 不能为空")
    private String instanceId;
}
