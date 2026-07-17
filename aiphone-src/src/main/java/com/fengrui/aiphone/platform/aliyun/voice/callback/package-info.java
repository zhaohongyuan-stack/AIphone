/**
 * 语音服务模块 - 回调接收层。
 *
 * <p>接收 NLS 平台推送的回调事件：
 * <ul>
 *   <li>实时转写结果推送 → 写入 dialogue_detail 表 + SSE 推送坐席前端</li>
 *   <li>TTS 合成完成</li>
 *   <li>录音文件转写完成</li>
 * </ul>
 *
 * <p>入口：{@code VoiceCallbackController}，路径 {@code /api/aliyun/voice/callback}</p>
 */
package com.fengrui.aiphone.platform.aliyun.voice.callback;
