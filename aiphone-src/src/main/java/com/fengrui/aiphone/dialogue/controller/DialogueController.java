package com.fengrui.aiphone.dialogue.controller;

import com.fengrui.aiphone.common.Result;
import com.fengrui.aiphone.dialogue.dto.req.DialogueSaveReq;
import com.fengrui.aiphone.dialogue.service.DialogueService;
import com.fengrui.aiphone.dialogue.vo.DialogueSaveVO;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 对话 SSE 接口。
 * <p>GET /api/dialogue/stream/{order_id}：SSE 长连接，实时推送对话转写文本。</p>
 * <p>POST /api/dialogue：保存对话明细（Python 端调用：直接落库）。</p>
 */
@RestController
@RequestMapping("/api/dialogue")
public class DialogueController {

    @Autowired
    private DialogueService dialogueService;

    /**
     * SSE 流式推送对话记录。
     * <p>连接后立即推送历史记录，然后保持挂起等待实时推送。超时 30 分钟。</p>
     */
    @GetMapping(value = "/stream/{order_id}", produces = "text/event-stream")
    public SseEmitter stream(@PathVariable("order_id") Long orderId) {
        return dialogueService.subscribe(orderId);
    }

    /** 保存对话明细（Python 端调用：直接落库） */
    @PostMapping
    public Result<DialogueSaveVO> save(@Valid @RequestBody DialogueSaveReq req) {
        return Result.success("对话保存成功",
                dialogueService.saveDirect(req.getOrderId(), req.getContent(), req.getRole()));
    }
}
