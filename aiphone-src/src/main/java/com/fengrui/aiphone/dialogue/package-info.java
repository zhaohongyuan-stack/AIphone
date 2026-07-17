/**
 * 业务模块：对话 / SSE 流式推送（dialogue）。
 *
 * <p>负责人：我（后端开发者）。承载对话明细存储与 SSE 实时推送。
 * 内部按 entity/mapper/service/controller/event 分层。</p>
 *
 * <p>对接阿里云智能语音交互（NLS）的实时 ASR 回调，
 * 转写文本写入 dialogue_detail 表后通过 SSE 推送给前端。</p>
 */
package com.fengrui.aiphone.dialogue;
