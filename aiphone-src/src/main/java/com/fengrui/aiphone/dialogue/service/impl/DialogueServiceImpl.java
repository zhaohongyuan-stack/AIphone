package com.fengrui.aiphone.dialogue.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fengrui.aiphone.dialogue.entity.DialogueDetail;
import com.fengrui.aiphone.dialogue.mapper.DialogueDetailMapper;
import com.fengrui.aiphone.dialogue.service.DialogueService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 对话服务实现。
 *
 * <p>Phase 7 改造：高频写场景用 Redis List 缓存，通话结束批量落库。
 * <ul>
 *   <li>SSE 超时 30 分钟，连接后推送历史记录，保持挂起等待实时推送</li>
 *   <li>完整句子 → 写 Redis List（dialogue:buffer:{orderId}）+ 推 SSE（不直接落库）</li>
 *   <li>中间结果 → 只推 SSE，不缓存不落库</li>
 *   <li>通话结束 → flushDialogueBuffer 批量写入 dialogue_detail + closeEmitter</li>
 * </ul></p>
 */
@Service
public class DialogueServiceImpl implements DialogueService {

    private static final Logger log = LoggerFactory.getLogger(DialogueServiceImpl.class);

    /** SSE 超时时间：30 分钟 */
    private static final long SSE_TIMEOUT = 30 * 60 * 1000L;

    /** msg_time 毫秒精度格式 */
    private static final DateTimeFormatter MSG_FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS");

    /** Redis 对话缓冲 key 前缀：dialogue:buffer:{orderId} */
    private static final String BUFFER_KEY_PREFIX = "dialogue:buffer:";

    /** Redis 缓冲 TTL：30 分钟（超时自动清理，防止异常未清理） */
    private static final long BUFFER_TTL_MINUTES = 30;

    /** 全局 emitter Map：orderId -> SseEmitter */
    private final Map<Long, SseEmitter> emitterMap = new ConcurrentHashMap<>();

    @Autowired
    private DialogueDetailMapper dialogueDetailMapper;

    @Autowired
    private RedisTemplate<String, Object> redisTemplate;

    @Override
    public SseEmitter subscribe(Long orderId) {
        SseEmitter emitter = new SseEmitter(SSE_TIMEOUT);
        emitterMap.put(orderId, emitter);

        // 注册回调，自动从 Map 移除，防内存泄漏
        emitter.onCompletion(() -> {
            emitterMap.remove(orderId);
            log.info("SSE 连接完成，orderId={} 已移除 emitter", orderId);
        });
        emitter.onError(e -> {
            emitterMap.remove(orderId);
            log.warn("SSE 连接异常，orderId={} 已移除 emitter: {}", orderId, e.getMessage());
        });
        emitter.onTimeout(() -> {
            emitterMap.remove(orderId);
            log.info("SSE 连接超时，orderId={} 已移除 emitter", orderId);
        });

        // 连接后立即推送历史记录（按 msg_time 升序）
        LambdaQueryWrapper<DialogueDetail> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(DialogueDetail::getOrderId, orderId)
               .orderByAsc(DialogueDetail::getMsgTime);
        List<DialogueDetail> history = dialogueDetailMapper.selectList(wrapper);
        for (DialogueDetail d : history) {
            try {
                emitter.send(SseEmitter.event().data(buildSseData(d.getDiaId(), d.getRole(), d.getContent(), d.getMsgTime(), true)));
            } catch (IOException e) {
                log.error("推送历史记录失败, diaId={}", d.getDiaId(), e);
            }
        }
        log.info("SSE 订阅成功，orderId={}, 推送历史记录 {} 条", orderId, history.size());

        // 不 complete，保持挂起等待实时推送
        return emitter;
    }

    @Override
    public void saveAndPush(Long orderId, String content, String role) {
        // 1. 缓存到 Redis List（不直接落库，通话结束批量写入）
        cacheDialogue(orderId, content, role);
        // 2. 推送 SSE
        pushOnly(orderId, content, role, true);
    }

    @Override
    public void pushOnly(Long orderId, String content, String role, Boolean finished) {
        SseEmitter emitter = emitterMap.get(orderId);
        if (emitter == null) {
            log.debug("SSE 推送跳过（无 emitter），orderId={}, finished={}", orderId, finished);
            return;
        }
        try {
            // dia_id 在落库前为 null，前端根据 finished 区分中间结果/完整句子
            Map<String, Object> data = buildSseData(null, role, content, LocalDateTime.now(), finished);
            emitter.send(SseEmitter.event().data(data));
            log.debug("SSE 推送成功, orderId={}, finished={}, role={}", orderId, finished, role);
        } catch (IOException e) {
            log.error("SSE 推送失败, orderId={}: {}", orderId, e.getMessage());
            emitterMap.remove(orderId);
        }
    }

    @Override
    public int flushDialogueBuffer(Long orderId) {
        String key = BUFFER_KEY_PREFIX + orderId;
        Long size = redisTemplate.opsForList().size(key);
        if (size == null || size == 0) {
            log.info("对话缓冲为空，无需落库: orderId={}", orderId);
            return 0;
        }

        // 从 Redis 读取全部对话明细
        List<Object> buffer = redisTemplate.opsForList().range(key, 0, -1);
        if (buffer == null || buffer.isEmpty()) {
            return 0;
        }

        // 批量构造实体并插入
        List<DialogueDetail> details = new ArrayList<>(buffer.size());
        for (Object item : buffer) {
            @SuppressWarnings("unchecked")
            Map<String, Object> entry = (Map<String, Object>) item;
            DialogueDetail d = new DialogueDetail();
            d.setOrderId(orderId);
            d.setContent((String) entry.get("content"));
            d.setRole((String) entry.get("role"));
            // msgTime 从缓存中恢复（存入时为 ISO 字符串）
            Object msgTimeObj = entry.get("msgTime");
            if (msgTimeObj instanceof String) {
                d.setMsgTime(LocalDateTime.parse((String) msgTimeObj, MSG_FMT));
            } else {
                d.setMsgTime(LocalDateTime.now());
            }
            details.add(d);
        }

        // 批量插入（MyBatis-Plus saveBatch 或循环 insert，此处用循环保证兼容）
        for (DialogueDetail d : details) {
            dialogueDetailMapper.insert(d);
        }

        // 删除 Redis 缓冲 Key
        redisTemplate.delete(key);

        log.info("对话缓冲已批量落库: orderId={}, 条数={}", orderId, details.size());
        return details.size();
    }

    @Override
    public void closeEmitter(Long orderId) {
        SseEmitter emitter = emitterMap.remove(orderId);
        if (emitter != null) {
            try {
                emitter.complete();
                log.info("SSE 连接已关闭: orderId={}", orderId);
            } catch (Exception e) {
                log.warn("SSE 关闭异常, orderId={}: {}", orderId, e.getMessage());
            }
        }
    }

    @Override
    public int activeEmitterCount() {
        return emitterMap.size();
    }

    /**
     * 缓存对话明细到 Redis List（不落库）。
     */
    private void cacheDialogue(Long orderId, String content, String role) {
        String key = BUFFER_KEY_PREFIX + orderId;
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("content", content);
        entry.put("role", role);
        entry.put("msgTime", LocalDateTime.now().format(MSG_FMT));
        redisTemplate.opsForList().rightPush(key, entry);
        // 设置 TTL，防止异常未清理
        redisTemplate.expire(key, BUFFER_TTL_MINUTES, TimeUnit.MINUTES);
    }

    /**
     * 构建 SSE 数据（JSON 格式，字段名 snake_case 对齐接口文档）。
     */
    private Map<String, Object> buildSseData(Long diaId, String role, String content, LocalDateTime msgTime, Boolean finished) {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("dia_id", diaId);
        data.put("role", role);
        data.put("content", content);
        data.put("msg_time", msgTime.format(MSG_FMT));
        data.put("finished", finished);
        return data;
    }
}
