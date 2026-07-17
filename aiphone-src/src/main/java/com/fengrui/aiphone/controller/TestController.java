package com.fengrui.aiphone.controller;

import com.fengrui.aiphone.common.Result;
import com.fengrui.aiphone.dialogue.service.DialogueService;
import com.fengrui.aiphone.platform.aliyun.ccc.config.CccProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 开发测试用 Controller（仅用于验证 SSE 推送管道和 CCC 事件分发，未接真实平台时的模拟入口）。
 * <p>生产环境应通过 ASR 回调（GummyAsrServiceImpl.AsrResultCallback#onEvent）触发 saveAndPush，
 * 而非此 Controller。</p>
 */
@RestController
@RequestMapping("/test")
public class TestController {

    private static final Logger log = LoggerFactory.getLogger(TestController.class);

    @Autowired
    private DialogueService dialogueService;

    @Autowired
    private RestTemplate restTemplate;

    @Autowired
    private CccProperties cccProperties;

    /**
     * 模拟推送：先存入 dialogue_detail 表，再通过 SSE 实时推送给已订阅该工单的前端。
     * <p>用法：POST /test/push/{orderId}?content=xxx&role=user</p>
     *
     * @param orderId  工单 ID
     * @param content  推送内容
     * @param role     发言角色（user/worker/AI/ivr），默认 user
     */
    @PostMapping("/push/{orderId}")
    public Result<Void> push(@PathVariable Long orderId,
                             @RequestParam String content,
                             @RequestParam(defaultValue = "user") String role) {
        log.info("[TEST] 模拟推送, orderId={}, role={}, content={}", orderId, role, content);
        dialogueService.saveAndPush(orderId, content, role);
        return Result.success("模拟推送成功", null);
    }

    /**
     * 查询当前活跃的 SSE 连接数（用于验证断开清理）。
     */
    @GetMapping("/emitters")
    public Result<Map<String, Object>> emitters() {
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("active_count", dialogueService.activeEmitterCount());
        return Result.success(data);
    }

    /**
     * 模拟 CCC 回调事件推送（本地自测事件分发流程）。
     * <p>用法：POST /test/ccc/event?eventType=Ringing&contactId=job-test-001&caller=13800138000&callee=05710000
     * <p>内部通过 RestTemplate 调用本机的 /api/aliyun/ccc/callback 接口，模拟 CCC Webhook 推送。
     * 用于验证事件分发流程（Controller 路由匹配 → Service 调用 → 日志输出）。</p>
     *
     * <p>推荐测试序列（来电 → 接听字幕 → 挂断归档）：
     * <ol>
     *   <li>eventType=Established&contactId=job-demo-001 → 创建工单</li>
     *   <li>eventType=TextStream&contactId=job-demo-001&text=你好 → 推送字幕（finished=true）</li>
     *   <li>eventType=Released&contactId=job-demo-001 → 停止 ASR + 归档</li>
     * </ol></p>
     *
     * @param eventType 事件类型（Ringing/Enqueue/AssignAgent/Abandoned/Established/Released/RecordingReady/TextStream/AgentCheckIn 等）
     * @param contactId 话务 ID（= jobId = conversation_id）
     * @param agentId   坐席 ID（可选，格式 agent@ccc-test）
     * @param caller     主叫号码（可选）
     * @param callee     被叫号码（可选）
     * @param text       识别文本（TextStream 专用，默认"你好，这是一条测试字幕"）
     * @param channelType 通道类型（TextStream 专用，agent/customer，默认 customer）
     * @param finished   是否句子结束（TextStream 专用，默认 true）
     * @param abandonPhase 放弃阶段（Abandoned 专用：IVR/Queuing/Ringing）
     * @param queueType  队列类型（AssignAgent/Abandoned 专用：Agent/SkillGroup）
     * @param skillGroupId 技能组 ID（可选）
     */
    @PostMapping("/ccc/event")
    public Result<Map<String, Object>> mockCccEvent(
            @RequestParam String eventType,
            @RequestParam(defaultValue = "job-test-001") String contactId,
            @RequestParam(required = false) String agentId,
            @RequestParam(required = false) String caller,
            @RequestParam(required = false) String callee,
            @RequestParam(defaultValue = "你好，这是一条测试字幕") String text,
            @RequestParam(defaultValue = "customer") String channelType,
            @RequestParam(defaultValue = "true") Boolean finished,
            @RequestParam(required = false) String abandonPhase,
            @RequestParam(required = false) String queueType,
            @RequestParam(required = false) String skillGroupId) {

        log.info("[TEST] 模拟 CCC 事件: eventType={}, contactId={}, agentId={}", eventType, contactId, agentId);

        // 构造 CCC 回调 JSON（话务类事件格式）
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("eventTime", java.time.OffsetDateTime.now().toString());
        event.put("eventType", eventType);
        // instanceId 从配置读取，确保与 CccCallbackSecurityUtil 校验一致
        String instanceId = cccProperties.getInstanceId();
        event.put("instanceId", instanceId != null ? instanceId : "ccc-test");
        // 话务类事件公共字段
        if (contactId != null) event.put("contactId", contactId);
        if (agentId != null) event.put("agentId", agentId);
        if (caller != null) event.put("caller", caller);
        if (callee != null) event.put("callee", callee);
        event.put("callType", "INBOUND");
        event.put("channelId", "ch-test-" + System.currentTimeMillis());
        event.put("mediaType", "Audio");
        // Released 事件特有字段
        if ("Released".equals(eventType)) {
            event.put("releaseInitiator", caller != null ? caller : "13800138000");
            event.put("releaseReason", "200 - Okay");
        }
        // RecordingReady 事件特有字段
        if ("RecordingReady".equals(eventType)) {
            event.put("startTime", java.time.OffsetDateTime.now().minusMinutes(5).toString());
            event.put("endTime", java.time.OffsetDateTime.now().toString());
            event.put("duration", 300);
            event.put("agentIds", agentId != null ? agentId : "agent@ccc-test");
            event.put("fileName", contactId + ".wav");
            event.put("downloadURL", "https://example.oss-cn-shanghai.aliyuncs.com/ccc-record/" + contactId + ".wav");
        }
        // TextStream 事件特有字段
        if ("TextStream".equals(eventType)) {
            event.put("text", text);
            event.put("channelType", channelType);
            event.put("finished", finished);
        }
        // Abandoned 事件特有字段
        if ("Abandoned".equals(eventType)) {
            event.put("abandonPhase", abandonPhase != null ? abandonPhase : "Queuing");
            event.put("contactFlowId", "test-flow-001");
            event.put("contactFlowType", "MAIN_FLOW");
            event.put("queueType", queueType != null ? queueType : "SkillGroup");
        }
        // AssignAgent 事件特有字段
        if ("AssignAgent".equals(eventType)) {
            event.put("queueType", queueType != null ? queueType : "SkillGroup");
        }
        // skillGroupId（AssignAgent/Ringing/Abandoned 等事件可携带）
        if (skillGroupId != null) {
            event.put("skillGroupId", skillGroupId);
        }

        // 通过 RestTemplate 调用本机 callback 接口
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(event, headers);

        try {
            String callbackUrl = "http://localhost:8080/api/aliyun/ccc/callback";
            org.springframework.http.ResponseEntity<String> resp = restTemplate.postForEntity(callbackUrl, entity, String.class);
            log.info("[TEST] CCC 事件分发完成: eventType={}, statusCode={}", eventType, resp.getStatusCode());

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("eventType", eventType);
            result.put("sentPayload", event);
            result.put("callbackResponse", resp.getBody());
            result.put("callbackStatus", resp.getStatusCode().value());
            return Result.success(result);
        } catch (Exception e) {
            log.error("[TEST] CCC 事件分发失败: {}", e.getMessage(), e);
            return Result.error("CCC 事件分发失败: " + e.getMessage());
        }
    }
}

