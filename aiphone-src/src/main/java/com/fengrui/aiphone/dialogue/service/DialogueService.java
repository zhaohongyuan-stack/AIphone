package com.fengrui.aiphone.dialogue.service;

import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * 对话服务接口（SSE 推送 + Redis 缓存 + 批量落库）。
 *
 * <p>Phase 7 改造：高频写场景用 Redis List 缓存，通话结束批量落库，避免频繁写云数据库。</p>
 */
public interface DialogueService {

    /**
     * 订阅指定工单的 SSE 流。
     * <p>连接后立即推送历史对话记录，然后保持挂起等待实时推送。</p>
     */
    SseEmitter subscribe(Long orderId);

    /**
     * 缓存对话明细到 Redis List + 实时推送到 SSE 前端（不直接落库）。
     * <p>完整句子（finished=true）调用此方法：写 Redis List（dialogue:buffer:{orderId}）+ 推 SSE。
     * 通话结束（Released）时由 {@link #flushDialogueBuffer(Long)} 批量写入 dialogue_detail 表。</p>
     *
     * @param orderId 工单 ID
     * @param content 文本内容
     * @param role    发言角色（user/worker/AI/ivr）
     */
    void saveAndPush(Long orderId, String content, String role);

    /**
     * 只推送 SSE，不缓存不落库（中间结果用）。
     * <p>中间结果（finished=false）调用此方法：仅推送到前端，不写 Redis，不落库。</p>
     *
     * @param orderId  工单 ID
     * @param content  文本内容
     * @param role     发言角色
     * @param finished 是否完整句子（前端据此决定"正在输入..."或固化显示）
     */
    void pushOnly(Long orderId, String content, String role, Boolean finished);

    /**
     * 批量落库：从 Redis List 读取全部缓存的对话明细，批量写入 dialogue_detail 表，然后删除 Redis Key。
     * <p>通话结束（Released 事件）时调用。</p>
     *
     * @param orderId 工单 ID
     * @return 落库条数
     */
    int flushDialogueBuffer(Long orderId);

    /**
     * 关闭指定工单的 SSE 连接（从 emitterMap 移除并 complete）。
     * <p>通话结束（Released 事件）时调用。</p>
     *
     * @param orderId 工单 ID
     */
    void closeEmitter(Long orderId);

    /**
     * 查询当前活跃的 SSE 连接数（仅用于开发测试验证连接清理）。
     */
    int activeEmitterCount();
}
