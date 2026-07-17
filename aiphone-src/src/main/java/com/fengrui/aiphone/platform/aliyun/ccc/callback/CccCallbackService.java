package com.fengrui.aiphone.platform.aliyun.ccc.callback;

import com.fengrui.aiphone.agent.entity.AgentInfo;
import com.fengrui.aiphone.agent.service.AgentInfoService;
import com.fengrui.aiphone.common.enums.AgentStatusEnum;
import com.fengrui.aiphone.common.enums.OrderStatusEnum;
import com.fengrui.aiphone.dialogue.service.DialogueService;
import com.fengrui.aiphone.platform.aliyun.ccc.callback.dto.*;
import com.fengrui.aiphone.platform.aliyun.ccc.ws.CallNotificationHandler;
import com.fengrui.aiphone.platform.aliyun.voice.service.GummyAsrService;
import com.fengrui.aiphone.workorder.service.WorkOrderService;
import com.fengrui.aiphone.workorder.vo.OrderCreateVO;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * CCC 回调事件处理服务。
 *
 * <p>核心业务流程：来电 → 接听字幕 → 挂断归档。
 * <ol>
 *   <li>{@link #handleRinging}：振铃 → 缓存来电信息到 Redis（待 Established 关联）</li>
 *   <li>{@link #handleEnqueue}：排队 → 仅日志（测试阶段）</li>
 *   <li>{@link #handleAssignAgent}：分配坐席 → 缓存 agentId 到 Redis（待 Established 关联）</li>
 *   <li>{@link #handleEstablished}：接通 → 创建工单 + 从 Redis 关联前置状态（agentId）</li>
 *   <li>{@link #handleTextStream}：实时字幕 → 中间结果只推 SSE；完整句子写 Redis List + 推 SSE</li>
 *   <li>{@link #handleReleased}：挂断 → 批量落库 + 关闭 SSE + 更新工单 + 清理 Redis</li>
 *   <li>{@link #handleAbandoned}：放弃 → 清理 Redis + 更新工单状态</li>
 *   <li>{@link #handleRecordingReady}：录音就绪 → 仅日志</li>
 *   <li>{@link #handleAgentEvent}：坐席事件 → 同步状态到 Redis + DB</li>
 * </ol></p>
 *
 * <p>Phase 7 改造：TextStream 不再直接落库，改为 Redis List 缓存 + SSE 推送，
 * 通话结束（Released）时批量写入 dialogue_detail。</p>
 */
@Service
public class CccCallbackService {

    private static final Logger log = LoggerFactory.getLogger(CccCallbackService.class);

    /** Redis 前置状态缓存 key 前缀：ccc:contact:{contactId}:meta */
    private static final String META_KEY_PREFIX = "ccc:contact:";

    /** Redis meta key 后缀 */
    private static final String META_KEY_SUFFIX = ":meta";

    /** Redis 缓存 TTL：30 分钟 */
    private static final long META_TTL_MINUTES = 30;

    @Autowired
    private WorkOrderService workOrderService;

    @Autowired
    private DialogueService dialogueService;

    @Autowired
    private GummyAsrService gummyAsrService;

    @Autowired
    private AgentInfoService agentInfoService;

    @Autowired
    private RedisTemplate<String, Object> redisTemplate;

    @Autowired
    private CallNotificationHandler callNotificationHandler;

    /**
     * contactId → orderId 映射（内存缓存，高频读，避免每次 TextStream 都查 Redis）。
     * <p>Established 创建工单后存入，TextStream 读取，Released 后移除。</p>
     */
    private final ConcurrentHashMap<String, Long> contextMap = new ConcurrentHashMap<>();

    // ==================== 通话事件 ====================

    /**
     * 处理 Ringing（振铃）事件。
     * <p>缓存来电信息到 Redis，待 Established 创建工单后关联。
     * 同时通过 WebSocket 广播新来电通知到所有已连接的坐席前端。</p>
     */
    public void handleRinging(RingingEventData event) {
        log.info("[CCC] 振铃事件: contactId={}, caller={}, callee={}, callType={}",
                event.getContactId(), event.getCaller(), event.getCallee(), event.getCallType());
        // 1. 缓存来电元信息到 Redis
        Map<String, Object> meta = new LinkedHashMap<>();
        meta.put("caller", event.getCaller());
        meta.put("callee", event.getCallee());
        meta.put("callType", event.getCallType());
        meta.put("skillGroupId", event.getSkillGroupId());
        String key = metaKey(event.getContactId());
        redisTemplate.opsForHash().putAll(key, meta);
        redisTemplate.expire(key, META_TTL_MINUTES, TimeUnit.MINUTES);

        // 2. WebSocket 广播新来电通知（坐席前端据此弹屏 + 请求历史工单）
        callNotificationHandler.broadcastNewCall(
                event.getContactId(),
                event.getCaller(),
                event.getCallee(),
                event.getCallType(),
                event.getSkillGroupId()
        );
    }

    /**
     * 处理 Enqueue（排队）事件。
     * <p>测试阶段仅记录日志，状态缓存待后续扩展。</p>
     */
    public void handleEnqueue(CccCallEventData event) {
        log.info("[CCC] 排队事件: contactId={}, caller={}, skillGroupId={}",
                event.getContactId(), event.getCaller(), event.getSkillGroupId());
    }

    /**
     * 处理 AssignAgent（分配坐席）事件。
     * <p>将 CCC agentId 缓存到 Redis，待 Established 创建工单后关联到 work_order.agent_id。</p>
     */
    public void handleAssignAgent(AssignAgentEventData event) {
        log.info("[CCC] 分配坐席: contactId={}, agentId={}, skillGroupId={}, queueType={}",
                event.getContactId(), event.getAgentId(), event.getSkillGroupId(), event.getQueueType());
        // 缓存 agentId 到 Redis
        String key = metaKey(event.getContactId());
        redisTemplate.opsForHash().put(key, "cccAgentId", event.getAgentId());
        redisTemplate.expire(key, META_TTL_MINUTES, TimeUnit.MINUTES);
    }

    /**
     * 处理 Established（通话建立）事件。
     *
     * <p>幂等查找逻辑：
     * <ol>
     *   <li>先用 contactId 查 work_order 表（conversation_id 字段）</li>
     *   <li>若已有工单（Python 在 IVR 阶段已创建）→ 更新状态为处理中 + 关联 agentId + 缓存 contextMap</li>
     *   <li>若无工单（异常兜底场景）→ 创建新工单</li>
     * </ol></p>
     *
     * <p>关联 agentId 来源优先级：
     * <ul>
     *   <li>事件本身携带的 agentId（Established 事件字段）</li>
     *   <li>Redis 缓存的 AssignAgent 事件 agentId</li>
     * </ul></p>
     */
    public void handleEstablished(EstablishedEventData event) {
        log.info("[CCC] 通话建立: contactId={}, agentId={}, caller={}, callee={}, skillGroupId={}",
                event.getContactId(), event.getAgentId(), event.getCaller(), event.getCallee(), event.getSkillGroupId());

        String contactId = event.getContactId();
        String instanceId = event.getInstanceId();

        // 1. 幂等查找：先查是否已有工单（Python 可能已在 IVR 阶段创建）
        com.fengrui.aiphone.workorder.entity.WorkOrder existOrder = workOrderService.findByConversationId(contactId);
        Long orderId;
        if (existOrder != null) {
            // 已有工单，更新状态为处理中（不覆盖已有字段，仅更新 order_status + agent_id）
            orderId = existOrder.getOrderId();
            log.info("[CCC] 工单已存在（Python 创建），复用: orderId={}, contactId={}", orderId, contactId);
            // 更新状态为处理中
            workOrderService.updateStatus(orderId, OrderStatusEnum.PROCESSING.getCode());
        } else {
            // 兜底创建（异常场景：Python 未创建）
            String phone = event.getCaller();
            OrderCreateVO vo = workOrderService.createOrder(phone, contactId, instanceId);
            orderId = vo.getOrderId();
            log.info("[CCC] 工单兜底创建: orderId={}, contactId={}, phone={}", orderId, contactId, phone);
        }

        // 2. 缓存 contextMap（后续 TextStream/Released 用）
        contextMap.put(contactId, orderId);

        // 3. 关联 agentId（优先用事件携带的 agentId，其次用 Redis 缓存的 AssignAgent）
        String cccAgentId = event.getAgentId();
        if (cccAgentId == null || cccAgentId.isBlank()) {
            cccAgentId = readMeta(contactId, "cccAgentId");
        }
        if (cccAgentId != null) {
            AgentInfo agent = agentInfoService.findByCccAgentId(cccAgentId);
            if (agent != null) {
                workOrderService.updateOrder(orderId, buildAgentUpdateReq(agent.getAgentId()));
                log.info("[CCC] 工单已关联坐席: orderId={}, agentId={}, cccAgentId={}",
                        orderId, agent.getAgentId(), cccAgentId);
            } else {
                log.warn("[CCC] 未找到本地坐席映射: cccAgentId={}, orderId={}", cccAgentId, orderId);
            }
        }

        // 4. WebSocket 通知前端"工单就绪"（前端拿到 orderId 后订阅 SSE）
        callNotificationHandler.broadcastOrderReady(contactId, orderId, event.getAgentId());

        log.info("[CCC] 工单就绪: contactId={}, orderId={}", contactId, orderId);
    }

    /**
     * 处理 TextStream（实时文本流）事件。
     * <p>中间结果（finished=false）→ 只推 SSE；完整句子（finished=true）→ 写 Redis List + 推 SSE。</p>
     */
    public void handleTextStream(TextStreamEventData event) {
        Long orderId = contextMap.get(event.getContactId());
        if (orderId == null) {
            log.warn("[CCC] TextStream 找不到 orderId: contactId={}", event.getContactId());
            return;
        }

        String role = resolveRole(event.getChannelType());
        Boolean finished = Boolean.TRUE.equals(event.getFinished());

        if (finished) {
            // 完整句子：写 Redis List（缓存）+ 推 SSE（不直接落库）
            dialogueService.saveAndPush(orderId, event.getText(), role);
            log.info("[CCC] 字幕已缓存+推送: orderId={}, role={}, text={}", orderId, role, event.getText());
        } else {
            // 中间结果：只推 SSE，不缓存不落库
            dialogueService.pushOnly(orderId, event.getText(), role, false);
            log.debug("[CCC] 字幕中间结果已推送: orderId={}, text={}", orderId, event.getText());
        }
    }

    /**
     * 处理 Released（挂机）事件。
     * <p>批量落库 + 关闭 SSE + 更新工单状态 + 清理 Redis。</p>
     */
    public void handleReleased(ReleasedEventData event) {
        log.info("[CCC] 挂机事件: contactId={}, releaseInitiator={}, releaseReason={}",
                event.getContactId(), event.getReleaseInitiator(), event.getReleaseReason());

        Long orderId = contextMap.remove(event.getContactId());
        if (orderId == null) {
            log.warn("[CCC] Released 找不到 orderId: contactId={}", event.getContactId());
            // 仍清理 Redis
            redisTemplate.delete(metaKey(event.getContactId()));
            return;
        }

        // 1. 批量落库对话明细（从 Redis List 读取，写入 dialogue_detail）
        int flushed = dialogueService.flushDialogueBuffer(orderId);
        log.info("[CCC] 对话明细已批量落库: orderId={}, 条数={}", orderId, flushed);

        // 2. 关闭 SSE 连接
        dialogueService.closeEmitter(orderId);

        // 3. 停止本地 ASR（如有）
        try {
            gummyAsrService.stopRecognition(orderId);
        } catch (Exception e) {
            log.debug("[CCC] 停止 ASR 异常（可忽略）: orderId={}, err={}", orderId, e.getMessage());
        }

        // 4. 更新工单状态为已办结 + call_end_time
        workOrderService.updateCallEndTime(orderId, 2); // 2-已办结
        log.info("[CCC] 工单已归档: orderId={}, orderStatus=2, contactId={}", orderId, event.getContactId());

        // 5. 清理 Redis 前置状态缓存
        redisTemplate.delete(metaKey(event.getContactId()));
    }

    /**
     * 处理 Abandoned（放弃）事件。
     * <p>客户在 IVR/排队/振铃阶段放弃通话。清理 Redis，若有工单则更新为主动挂断。</p>
     */
    public void handleAbandoned(AbandonedEventData event) {
        log.info("[CCC] 放弃事件: contactId={}, abandonPhase={}, agentId={}, skillGroupId={}",
                event.getContactId(), event.getAbandonPhase(), event.getAgentId(), event.getSkillGroupId());

        // 若已有工单（Established 已创建），更新为主动挂断
        Long orderId = contextMap.remove(event.getContactId());
        if (orderId != null) {
            dialogueService.flushDialogueBuffer(orderId);
            dialogueService.closeEmitter(orderId);
            workOrderService.updateCallEndTime(orderId, 0); // 0-主动挂断
            log.info("[CCC] 放弃后工单已更新: orderId={}, status=0", orderId);
        }

        // 清理 Redis 前置状态缓存
        redisTemplate.delete(metaKey(event.getContactId()));
    }

    /**
     * 处理 RecordingReady（录音生成）事件。
     * <p>录音不保存，只打日志。</p>
     */
    public void handleRecordingReady(RecordingReadyEventData event) {
        log.info("[CCC] 录音生成（不保存）: contactId={}, fileName={}, duration={}s",
                event.getContactId(), event.getFileName(), event.getDuration());
    }

    // ==================== 坐席事件 ====================

    /**
     * 处理坐席事件（通用）。
     * <p>坐席事件包括：AgentCheckIn/AgentReady/AgentBreak/AgentCheckOut 等。
     * 通过 ccc_agent_id 查本地 agent_id，同步状态到 Redis + DB。</p>
     */
    public void handleAgentEvent(String eventType, CccAgentEventData event) {
        log.info("[CCC] 坐席事件: eventType={}, agentId={}, skillGroupIds={}",
                eventType, event.getAgentId(), event.getSkillGroupIds());
        Integer status = resolveAgentStatus(eventType);
        if (status == null) {
            log.debug("[CCC] 坐席事件无需同步状态: eventType={}", eventType);
            return;
        }
        agentInfoService.updateStatus(event.getAgentId(), status);
        log.info("[CCC] 坐席状态已同步: cccAgentId={}, status={}", event.getAgentId(), status);
    }

    /**
     * 处理未识别的事件类型。
     */
    public void handleUnknownEvent(String eventType, String requestBody) {
        log.warn("[CCC] 未处理的事件类型: eventType={}, body={}", eventType, requestBody);
    }

    // ==================== 工具方法 ====================

    /**
     * 将 CCC 的 channelType 映射为本地对话角色。
     * <p>agent → worker，customer → user，默认 user。</p>
     */
    private String resolveRole(String channelType) {
        if (channelType == null) {
            return "user";
        }
        return "agent".equalsIgnoreCase(channelType) ? "worker" : "user";
    }

    /**
     * 解析坐席事件类型为本地状态码。
     * <p>0-离线 1-正忙 2-在线空闲</p>
     */
    private Integer resolveAgentStatus(String eventType) {
        switch (eventType) {
            case "AgentCheckIn":
            case "AgentReady":
                return AgentStatusEnum.ONLINE.getCode();
            case "AgentDialing":
            case "AgentRinging":
            case "AgentTalk":
            case "AgentRelease":
            case "AgentBreak":
                return AgentStatusEnum.BUSY.getCode();
            case "AgentCheckOut":
            case "AgentRingingTimeout":
                return AgentStatusEnum.OFFLINE.getCode();
            default:
                return null;
        }
    }

    /**
     * 构建 Redis meta key。
     */
    private String metaKey(String contactId) {
        return META_KEY_PREFIX + contactId + META_KEY_SUFFIX;
    }

    /**
     * 从 Redis Hash 读取单个 meta 字段。
     */
    private String readMeta(String contactId, String field) {
        Object val = redisTemplate.opsForHash().get(metaKey(contactId), field);
        return val != null ? val.toString() : null;
    }

    /**
     * 构造只更新 agentId 的 OrderUpdateReq。
     * <p>使用反射避免引入 OrderUpdateReq 依赖，直接用现有 updateOrder 方法。</p>
     */
    private com.fengrui.aiphone.workorder.dto.req.OrderUpdateReq buildAgentUpdateReq(Long agentId) {
        com.fengrui.aiphone.workorder.dto.req.OrderUpdateReq req = new com.fengrui.aiphone.workorder.dto.req.OrderUpdateReq();
        req.setAgentId(agentId);
        return req;
    }
}
