package com.fengrui.aiphone.platform.aliyun.voice.service;

/**
 * Gummy 实时语音识别（ASR）服务接口。
 * <p>识别任务提交到独立线程池异步执行，不阻塞 Tomcat 请求线程。</p>
 */
public interface GummyAsrService {

    /**
     * 启动指定工单的实时语音识别。
     * <p>构建 TranslationRecognizerParam，创建实例，提交 ASR 线程池执行。</p>
     */
    void startRecognition(Long orderId);

    /**
     * 发送音频帧到识别实例（1024 字节分片）。
     */
    void sendAudioFrame(Long orderId, byte[] audioData);

    /**
     * 停止指定工单的识别（阻塞直至回调完成），finally 中关闭 WebSocket。
     */
    void stopRecognition(Long orderId);
}
