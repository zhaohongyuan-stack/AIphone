package com.fengrui.aiphone.platform.aliyun.voice.service.impl;

import com.alibaba.dashscope.audio.asr.translation.TranslationRecognizerParam;
import com.alibaba.dashscope.audio.asr.translation.TranslationRecognizerRealtime;
import com.alibaba.dashscope.audio.asr.translation.results.TranscriptionResult;
import com.alibaba.dashscope.audio.asr.translation.results.TranslationRecognizerResult;
import com.alibaba.dashscope.common.ResultCallback;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fengrui.aiphone.dialogue.service.DialogueService;
import com.fengrui.aiphone.platform.aliyun.voice.service.GummyAsrService;
import com.fengrui.aiphone.workorder.entity.WorkOrder;
import com.fengrui.aiphone.workorder.mapper.WorkOrderMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.nio.ByteBuffer;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Gummy 实时语音识别（ASR）服务实现。
 *
 * <p>基于阿里云 DashScope SDK 2.22.18 的 {@link TranslationRecognizerRealtime}，
 * 使用 gummy-realtime-v1 模型进行实时语音转写。</p>
 *
 * <h3>强制规范对齐</h3>
 * <ul>
 *   <li>识别任务提交到独立线程池（{@code asrExecutor}）异步执行，严禁阻塞 Tomcat 请求线程</li>
 *   <li>WebSocket 连接释放（{@code translator.getDuplexApi().close()}）必须写在 finally 块中</li>
 *   <li>仅 {@code isSentenceEnd=true} 的完整句子才落库 + SSE 推送，中间结果只推前端不存库</li>
 *   <li>只开识别（{@code transcriptionEnabled=true}），关闭翻译（{@code translationEnabled=false}）节省费用</li>
 *   <li>发生异常自动重连最多 3 次，3 次均失败则标记该工单转写异常（更新 {@code ai_failure_note}）</li>
 * </ul>
 *
 * <h3>角色映射说明</h3>
 * <p>gummy-realtime-v1 模型为单声道（mono）PCM 输入，{@link TranscriptionResult} 不区分 channelId。
 * 所有识别结果统一标记为 {@code "user"} 角色（来电方）。如需区分坐席方（worker），
 * 需切换为双声道模型并在 {@code AsrResultCallback#resolveRole} 中扩展。</p>
 */
@Service
public class GummyAsrServiceImpl implements GummyAsrService {

    private static final Logger log = LoggerFactory.getLogger(GummyAsrServiceImpl.class);

    /** 最大重试次数（3 次均失败后标记工单异常） */
    private static final int MAX_RETRIES = 3;

    /** 60 秒续传阈值（毫秒），接近该时长且句子结束时自动重启识别 */
    private static final long SEGMENT_DURATION_MS = 60_000L;

    /** 音频帧分片大小（字节） */
    private static final int AUDIO_CHUNK_SIZE = 1024;

    /** 重连等待时间（毫秒） */
    private static final long RETRY_DELAY_MS = 1000L;

    /** WebSocket 关闭码（正常关闭） */
    private static final int WS_CLOSE_CODE = 1000;

    /** WebSocket 关闭原因 */
    private static final String WS_CLOSE_REASON = "normal close";

    /** 异常标记文案（写入 work_order.ai_failure_note） */
    private static final String FAILURE_NOTE = "ASR transcription failed after 3 retries";

    /** 实例管理：orderId → 识别实例 */
    private final ConcurrentHashMap<Long, TranslationRecognizerRealtime> recognizerMap = new ConcurrentHashMap<>();

    /** 重试计数：orderId → 当前重试次数（AtomicInteger 保证并发自增安全） */
    private final ConcurrentHashMap<Long, AtomicInteger> retryCountMap = new ConcurrentHashMap<>();

    /** 识别开始时间：orderId → 开始时间戳（用于 60 秒续传判定） */
    private final ConcurrentHashMap<Long, Long> startTimeMap = new ConcurrentHashMap<>();

    @Qualifier("asrExecutor")
    @Autowired
    private ExecutorService asrExecutor;

    @Autowired
    private DialogueService dialogueService;

    @Autowired
    private WorkOrderMapper workOrderMapper;

    @Value("${aliyun.voice.api-key:}")
    private String apiKey;

    @Value("${aliyun.voice.model:gummy-realtime-v1}")
    private String model;

    @Value("${aliyun.voice.format:pcm}")
    private String format;

    @Value("${aliyun.voice.sample-rate:16000}")
    private Integer sampleRate;

    @Value("${aliyun.voice.source-language:zh}")
    private String sourceLanguage;

    /**
     * 启动指定工单的实时语音识别。
     * <p>构建 {@link TranslationRecognizerParam}，创建实例，提交 ASR 线程池执行。</p>
     */
    @Override
    public void startRecognition(Long orderId) {
        if (orderId == null) {
            throw new IllegalArgumentException("orderId 不能为空");
        }
        if (apiKey == null || apiKey.isBlank()) {
            log.error("ASR 启动失败：未配置 aliyun.voice.api-key，orderId={}", orderId);
            throw new IllegalStateException("DASHSCOPE_API_KEY 未配置，无法启动 ASR");
        }

        // 1. 构建识别参数（仅开识别，关闭翻译节省费用）
        TranslationRecognizerParam param = TranslationRecognizerParam.builder()
                .model(model)
                .apiKey(apiKey)
                .format(format)
                .sampleRate(sampleRate)
                .transcriptionEnabled(true)
                .translationEnabled(false)
                .sourceLanguage(sourceLanguage)
                .build();

        // 2. 创建识别实例（显式传 apiKey，避免依赖环境变量）
        TranslationRecognizerRealtime recognizer = new TranslationRecognizerRealtime(apiKey);

        // 3. 注册到 Map + 记录开始时间（putIfAbsent 保证重连时不重置重试计数）
        recognizerMap.put(orderId, recognizer);
        startTimeMap.put(orderId, System.currentTimeMillis());
        retryCountMap.putIfAbsent(orderId, new AtomicInteger(0));

        // 4. 提交 ASR 线程池异步执行（call 阻塞，必须在 asrExecutor 中运行）
        asrExecutor.execute(() -> {
            try {
                recognizer.call(param, new AsrResultCallback(orderId));
            } catch (Exception e) {
                log.error("ASR call 启动异常, orderId={}", orderId, e);
                // call 抛异常时手动触发 onError 流程
                new AsrResultCallback(orderId).onError(e);
            }
        });

        log.info("ASR 识别已启动, orderId={}, model={}, format={}, sampleRate={}",
                orderId, model, format, sampleRate);
    }

    /**
     * 发送音频帧到识别实例（1024 字节分片）。
     */
    @Override
    public void sendAudioFrame(Long orderId, byte[] audioData) {
        if (orderId == null || audioData == null || audioData.length == 0) {
            return;
        }
        TranslationRecognizerRealtime recognizer = recognizerMap.get(orderId);
        if (recognizer == null) {
            log.warn("ASR 实例不存在, orderId={}, 忽略音频帧（可能未启动或已停止）", orderId);
            return;
        }

        // 1024 字节分片发送
        int offset = 0;
        while (offset < audioData.length) {
            int length = Math.min(AUDIO_CHUNK_SIZE, audioData.length - offset);
            ByteBuffer buffer = ByteBuffer.wrap(audioData, offset, length);
            try {
                recognizer.sendAudioFrame(buffer);
            } catch (Exception e) {
                log.error("发送音频帧失败, orderId={}, offset={}", orderId, offset, e);
                throw new RuntimeException("发送音频帧失败", e);
            }
            offset += length;
        }
        if (log.isDebugEnabled()) {
            log.debug("音频帧已发送, orderId={}, bytes={}", orderId, audioData.length);
        }
    }

    /**
     * 停止指定工单的识别（阻塞直至回调完成），finally 中关闭 WebSocket 并移除实例。
     */
    @Override
    public void stopRecognition(Long orderId) {
        TranslationRecognizerRealtime recognizer = recognizerMap.remove(orderId);
        if (recognizer == null) {
            log.warn("ASR 实例不存在, orderId={}, stopRecognition 跳过", orderId);
            return;
        }

        // 【强制规范】stop + close 必须成对出现，close 必须在 finally 块
        try {
            // stop 阻塞直至回调完成
            recognizer.stop();
            log.info("ASR stop 完成, orderId={}", orderId);
        } catch (Exception e) {
            log.error("ASR stop 异常, orderId={}", orderId, e);
        } finally {
            try {
                boolean closed = recognizer.getDuplexApi().close(WS_CLOSE_CODE, WS_CLOSE_REASON);
                log.info("WebSocket 关闭, orderId={}, result={}", orderId, closed);
            } catch (Exception e) {
                log.error("WebSocket 关闭异常, orderId={}", orderId, e);
            }
        }

        // 清理辅助 Map
        startTimeMap.remove(orderId);
        retryCountMap.remove(orderId);
        log.info("ASR 识别已停止, orderId={}, 资源已释放", orderId);
    }

    // ==================== 内部辅助方法 ====================

    /**
     * 角色解析：channelId 0 → user，1 → worker。
     * <p>gummy-realtime-v1 单声道模型不返回 channelId，统一返回 "user"。</p>
     */
    private String resolveRole(Integer channelId) {
        if (channelId == null) {
            return "user";
        }
        return channelId == 1 ? "worker" : "user";
    }

    /**
     * 清理旧实例（重连前调用），stop + close 成对出现。
     */
    private void cleanupOldInstance(Long orderId) {
        TranslationRecognizerRealtime old = recognizerMap.remove(orderId);
        if (old == null) {
            return;
        }
        try {
            old.stop();
        } catch (Exception e) {
            log.warn("清理旧实例 stop 异常, orderId={}: {}", orderId, e.getMessage());
        } finally {
            try {
                old.getDuplexApi().close(WS_CLOSE_CODE, "cleanup before retry");
            } catch (Exception e) {
                log.warn("清理旧实例 close 异常, orderId={}: {}", orderId, e.getMessage());
            }
        }
    }

    /**
     * 更新工单 ai_failure_note（标记转写异常）。
     */
    private void updateFailureNote(Long orderId, String note) {
        try {
            LambdaUpdateWrapper<WorkOrder> wrapper = new LambdaUpdateWrapper<>();
            wrapper.eq(WorkOrder::getOrderId, orderId)
                   .set(WorkOrder::getAiFailureNote, note);
            workOrderMapper.update(null, wrapper);
            log.warn("工单转写异常已标记, orderId={}, note={}", orderId, note);
        } catch (Exception e) {
            log.error("更新 ai_failure_note 失败, orderId={}", orderId, e);
        }
    }

    // ==================== ResultCallback 内部类 ====================

    /**
     * ASR 结果回调实现。
     * <ul>
     *   <li>{@code onEvent}：判断 isSentenceEnd，true 则落库 + SSE 推送，false 仅日志</li>
     *   <li>{@code onError}：重试 &lt; 3 次则重连，否则更新 ai_failure_note</li>
     *   <li>{@code onComplete}：清理实例缓存</li>
     * </ul>
     */
    private class AsrResultCallback extends ResultCallback<TranslationRecognizerResult> {

        private final Long orderId;

        AsrResultCallback(Long orderId) {
            this.orderId = orderId;
        }

        @Override
        public void onEvent(TranslationRecognizerResult result) {
            if (result == null) {
                return;
            }
            TranscriptionResult transcription = result.getTranscriptionResult();
            if (transcription == null) {
                return;
            }
            String text = transcription.getText();
            boolean sentenceEnd = result.isSentenceEnd();

            if (sentenceEnd) {
                // 【强制规范】仅 isSentenceEnd=true 的完整句子才落库 + SSE 推送
                if (text != null && !text.isBlank()) {
                    String role = resolveRole(null); // gummy-realtime-v1 单声道，统一 user
                    try {
                        dialogueService.saveAndPush(orderId, text, role);
                        log.info("ASR 完整句子已落库并推送, orderId={}, role={}, text={}",
                                orderId, role, text);
                    } catch (Exception e) {
                        log.error("saveAndPush 失败, orderId={}", orderId, e);
                    }
                }
                // 60 秒续传机制：接近 60 秒且当前句子已结束，自动 stop + restart
                Long startTime = startTimeMap.get(orderId);
                if (startTime != null) {
                    long elapsed = System.currentTimeMillis() - startTime;
                    if (elapsed >= SEGMENT_DURATION_MS) {
                        log.info("ASR 接近 60 秒，触发续传, orderId={}, elapsed={}ms",
                                orderId, elapsed);
                        restartForContinuation(orderId);
                    }
                }
            } else {
                // 【强制规范】中间结果只推前端不存库 - 此处仅日志输出
                if (log.isDebugEnabled()) {
                    log.debug("ASR 中间结果, orderId={}, text={}", orderId, text);
                }
            }
        }

        @Override
        public void onComplete() {
            log.info("ASR 回调完成, orderId={}", orderId);
            // 不在此处 remove recognizerMap，由 stopRecognition 统一清理
            // 但清理辅助 Map（识别已结束，时间不再需要）
            startTimeMap.remove(orderId);
        }

        @Override
        public void onError(Exception e) {
            log.error("ASR 识别异常, orderId={}, error={}", orderId, e.getMessage(), e);
            AtomicInteger retry = retryCountMap.computeIfAbsent(orderId, k -> new AtomicInteger(0));
            int current = retry.get();
            if (current < MAX_RETRIES) {
                retry.incrementAndGet();
                log.warn("ASR 自动重连, orderId={}, 重试次数={}/{}", orderId, retry.get(), MAX_RETRIES);
                // 1. 清理旧实例（stop + close 成对）
                cleanupOldInstance(orderId);
                // 2. 短暂等待避免立即重连打爆服务
                try {
                    Thread.sleep(RETRY_DELAY_MS);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    log.warn("ASR 重连等待被中断, orderId={}", orderId);
                    return;
                }
                // 3. 重新启动识别（startRecognition 会重新提交 asrExecutor）
                try {
                    startRecognition(orderId);
                } catch (Exception restartEx) {
                    log.error("ASR 重连失败, orderId={}", orderId, restartEx);
                    updateFailureNote(orderId, FAILURE_NOTE + ": " + restartEx.getMessage());
                    cleanupOldInstance(orderId);
                }
            } else {
                // 【强制规范】3 次失败更新 ai_failure_note
                log.error("ASR 重连 {} 次均失败, orderId={}, 标记工单转写异常",
                        MAX_RETRIES, orderId);
                updateFailureNote(orderId, FAILURE_NOTE);
                cleanupOldInstance(orderId);
                retryCountMap.remove(orderId);
                startTimeMap.remove(orderId);
            }
        }

        /**
         * 60 秒续传：先 stop 旧实例（含 close），再 startRecognition。
         * <p>注意：不增加重试计数（这是正常续传，非异常重连）。</p>
         */
        private void restartForContinuation(Long orderId) {
            try {
                // 复用 stopRecognition 清理旧实例（含 finally close）
                // 但 stopRecognition 会 remove retryCountMap，所以先保存再恢复
                AtomicInteger savedRetry = retryCountMap.get(orderId);
                stopRecognition(orderId);
                if (savedRetry != null) {
                    retryCountMap.put(orderId, savedRetry);
                }
                // 重新启动（不计入重试）
                startRecognition(orderId);
                log.info("ASR 60 秒续传完成, orderId={}", orderId);
            } catch (Exception e) {
                log.error("ASR 续传失败, orderId={}", orderId, e);
                // 续传失败按异常处理
                onError(e);
            }
        }
    }
}
