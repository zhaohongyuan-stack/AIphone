/**
 * 阿里云语音（Voice）模块 - 实时语音识别（ASR）服务实现层。
 *
 * <p>当前阶段实现 Gummy 实时语音识别（{@code GummyAsrServiceImpl}），基于
 * DashScope SDK 2.22.18 的 {@code TranslationRecognizerRealtime}。</p>
 *
 * <p>核心特性：</p>
 * <ul>
 *   <li>识别任务提交到独立线程池（{@code asrExecutor}）异步执行，不阻塞 Tomcat 请求线程</li>
 *   <li>仅开启识别（{@code transcriptionEnabled=true}），关闭翻译（{@code translationEnabled=false}）节省费用</li>
 *   <li>仅 {@code isSentenceEnd=true} 的完整句子落库 + SSE 推送，中间结果仅日志</li>
 *   <li>异常自动重连最多 3 次，3 次失败则更新 {@code work_order.ai_failure_note}</li>
 *   <li>60 秒续传机制：长通话自动 stop + restart 防止识别中断</li>
 *   <li>所有 WebSocket 资源释放（{@code stop()} / {@code getDuplexApi().close()}）在 finally 块成对出现</li>
 * </ul>
 */
package com.fengrui.aiphone.platform.aliyun.voice.service.impl;
