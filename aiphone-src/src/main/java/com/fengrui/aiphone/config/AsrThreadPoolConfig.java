package com.fengrui.aiphone.config;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/**
 * ASR 语音识别专用线程池配置。
 * <p>识别任务必须提交到独立线程池异步执行，严禁阻塞 Tomcat 请求线程。</p>
 * <p>应用关闭时（@PreDestroy）优雅停机，释放所有 WebSocket 连接。</p>
 */
@Configuration
public class AsrThreadPoolConfig {

    private static final Logger log = LoggerFactory.getLogger(AsrThreadPoolConfig.class);

    private ThreadPoolExecutor asrExecutorInstance;

    @Bean("asrExecutor")
    public ExecutorService asrExecutor() {
        // 核心线程数 = 可用处理器数 * 2
        int core = Runtime.getRuntime().availableProcessors() * 2;
        asrExecutorInstance = new ThreadPoolExecutor(
                core,
                core,
                60L, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(100),
                r -> {
                    Thread t = new Thread(r, "asr-worker-" + System.currentTimeMillis());
                    t.setDaemon(true);
                    return t;
                },
                new ThreadPoolExecutor.CallerRunsPolicy()
        );
        log.info("ASR 线程池初始化完成，核心线程数={}", core);
        return asrExecutorInstance;
    }

    /**
     * 应用关闭时优雅停机，等待正在执行的识别任务完成。
     */
    @PreDestroy
    public void shutdown() {
        if (asrExecutorInstance != null) {
            log.info("ASR 线程池优雅停机开始...");
            asrExecutorInstance.shutdown();
            try {
                if (!asrExecutorInstance.awaitTermination(10, TimeUnit.SECONDS)) {
                    asrExecutorInstance.shutdownNow();
                }
            } catch (InterruptedException e) {
                asrExecutorInstance.shutdownNow();
                Thread.currentThread().interrupt();
            }
            log.info("ASR 线程池已停机");
        }
    }
}
