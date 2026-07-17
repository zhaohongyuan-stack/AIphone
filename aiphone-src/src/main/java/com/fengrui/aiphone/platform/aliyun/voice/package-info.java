/**
 * 阿里云智能语音交互（NLS）对接模块。
 *
 * <p>负责实时语音转写（ASR）、一句话识别、TTS 合成、录音文件识别等能力。
 * 包含三个子包：
 * <ul>
 *   <li>{@code callback} - 接收 NLS 推送的转写结果、TTS 完成等回调</li>
 *   <li>{@code client} - 主动调用 NLS API</li>
 *   <li>{@code config} - NLS 连接配置（AppKey、Token、服务地址等）</li>
 * </ul>
 *
 * <p>回调入口路径：{@code /api/aliyun/voice/callback}</p>
 *
 * <p>对接资料：docs/实时语音客服系统.md（DashScope SDK + TranslationRecognizerRealtime）。</p>
 */
package com.fengrui.aiphone.platform.aliyun.voice;
