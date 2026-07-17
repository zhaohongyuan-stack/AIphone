package com.fengrui.aiphone.platform.aliyun.ccc.callback;

import com.fengrui.aiphone.common.Result;
import com.fengrui.aiphone.platform.aliyun.ccc.callback.dto.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * CCC 回调接收接口。
 *
 * <p>接收阿里云云联络中心（CCC）的 Webhook 回调事件。
 * 配置方式：在 CCC 控制台调用 UpdateSubscription API，配置 Webhook 回调地址为
 * {@code https://your-domain.com/api/aliyun/ccc/callback}。</p>
 *
 * <p>请求格式：POST + application/json
 * 签名校验：❌ 不支持（UpdateSubscription API 无签名相关参数），
 * 采用 {@link CccCallbackSecurityUtil} 的 instanceId 校验 + IP 白名单（预留）。</p>
 *
 * <p>事件分发流程：
 * <ol>
 *   <li>解析公共字段（eventType/instanceId）</li>
 *   <li>安全校验（instanceId）</li>
 *   <li>根据 eventType 分发到 {@link CccCallbackService} 对应方法</li>
 * </ol></p>
 */
@RestController
@RequestMapping("/api/aliyun/ccc")
public class CccCallbackController {

    private static final Logger log = LoggerFactory.getLogger(CccCallbackController.class);

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private CccCallbackService cccCallbackService;

    @Autowired
    private CccCallbackSecurityUtil securityUtil;

    /**
     * CCC 回调接收接口。
     *
     * @param requestBody JSON 请求体（原始字符串，用于二次解析）
     * @param request    HTTP 请求对象（用于获取客户端 IP）
     * @return 处理结果
     */
    @PostMapping("/callback")
    public Result<Void> handleCallback(@RequestBody String requestBody, HttpServletRequest request) {
        try {
            log.info("[CCC] 收到回调: body={}", requestBody);

            // 1. 解析公共字段
            CccCallbackRequest baseRequest = objectMapper.readValue(requestBody, CccCallbackRequest.class);
            String eventType = baseRequest.getEventType();
            String instanceId = baseRequest.getInstanceId();

            // 2. 安全校验
            String clientIp = getClientIp(request);
            if (!securityUtil.validateIp(clientIp)) {
                log.warn("[CCC] IP 白名单校验失败: ip={}", clientIp);
                return Result.error("IP not allowed");
            }
            if (!securityUtil.validateInstanceId(instanceId)) {
                log.warn("[CCC] instanceId 校验失败: instanceId={}", instanceId);
                return Result.error("Invalid instanceId");
            }

            // 3. 根据 eventType 分发到对应处理方法
            dispatchEvent(eventType, requestBody);
            return Result.success("回调处理成功", null);

        } catch (Exception e) {
            log.error("[CCC] 回调处理异常: {}", e.getMessage(), e);
            return Result.error("回调处理异常: " + e.getMessage());
        }
    }

    /**
     * 根据 eventType 分发到对应处理方法。
     *
     * <p>本阶段仅处理 4 个关键事件（Ringing/Established/Released/RecordingReady）+ 坐席事件，
     * 其余事件用 {@link CccCallbackService#handleUnknownEvent} 记录日志。</p>
     */
    private void dispatchEvent(String eventType, String requestBody) throws Exception {
        if (eventType == null) {
            log.warn("[CCC] eventType 为空: body={}", requestBody);
            return;
        }
        switch (eventType) {
            case "Ringing":
                RingingEventData ringing = objectMapper.readValue(requestBody, RingingEventData.class);
                cccCallbackService.handleRinging(ringing);
                break;
            case "Enqueue":
                CccCallEventData enqueue = objectMapper.readValue(requestBody, CccCallEventData.class);
                cccCallbackService.handleEnqueue(enqueue);
                break;
            case "AssignAgent":
                AssignAgentEventData assignAgent = objectMapper.readValue(requestBody, AssignAgentEventData.class);
                cccCallbackService.handleAssignAgent(assignAgent);
                break;
            case "Abandoned":
                AbandonedEventData abandoned = objectMapper.readValue(requestBody, AbandonedEventData.class);
                cccCallbackService.handleAbandoned(abandoned);
                break;
            case "Established":
                EstablishedEventData established = objectMapper.readValue(requestBody, EstablishedEventData.class);
                cccCallbackService.handleEstablished(established);
                break;
            case "Released":
                ReleasedEventData released = objectMapper.readValue(requestBody, ReleasedEventData.class);
                cccCallbackService.handleReleased(released);
                break;
            case "RecordingReady":
                RecordingReadyEventData recording = objectMapper.readValue(requestBody, RecordingReadyEventData.class);
                cccCallbackService.handleRecordingReady(recording);
                break;
            case "TextStream":
                TextStreamEventData textStream = objectMapper.readValue(requestBody, TextStreamEventData.class);
                cccCallbackService.handleTextStream(textStream);
                break;
            case "AgentCheckIn":
            case "AgentReady":
            case "AgentDialing":
            case "AgentRinging":
            case "AgentTalk":
            case "AgentRelease":
            case "AgentBreak":
            case "AgentCheckOut":
            case "AgentRingingTimeout":
                CccAgentEventData agentEvent = objectMapper.readValue(requestBody, CccAgentEventData.class);
                cccCallbackService.handleAgentEvent(eventType, agentEvent);
                break;
            default:
                cccCallbackService.handleUnknownEvent(eventType, requestBody);
                break;
        }
    }

    /**
     * 获取客户端真实 IP（考虑代理转发）。
     */
    private String getClientIp(HttpServletRequest request) {
        String ip = request.getHeader("X-Forwarded-For");
        if (ip == null || ip.isBlank() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getHeader("X-Real-IP");
        }
        if (ip == null || ip.isBlank() || "unknown".equalsIgnoreCase(ip)) {
            ip = request.getRemoteAddr();
        }
        // 多级代理时取第一个
        if (ip != null && ip.contains(",")) {
            ip = ip.split(",")[0].trim();
        }
        return ip;
    }
}
