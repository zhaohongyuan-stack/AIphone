package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC RecordingReady（录音生成）事件数据。
 *
 * <p>触发场景：录音文件生成完成。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>我方处理：可选触发录音文件下载和转写（本阶段实时 ASR 已由 Gummy 覆盖，
 * 录音转写作为备份方案预留）。{@link #downloadURL} 有过期时间，需及时下载。</p>
 *
 * <p>注意：继承 {@link CccCallbackRequest}（非话务类基类），因为录音生成事件
 * 不包含话务类公共字段（如 channelId/caller/callee 等）。</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class RecordingReadyEventData extends CccCallbackRequest {

    /**
     * 录音开始时间（UTC）。
     * <p>呼入场景下为转人工接听时间，呼出场景为拨号后用户接听时间。</p>
     * 示例值：2021-04-14T01:56:55Z
     */
    @JsonProperty("startTime")
    private String startTime;

    /**
     * 录音结束时间（UTC）。
     * <p>如果没有发起满意度调查，则为通话结束时间；否则为坐席发起满意度调查的时间。</p>
     * 示例值：2021-04-14T01:57:25Z
     */
    @JsonProperty("endTime")
    private String endTime;

    /**
     * 录音时长（单位：秒）。
     * <p>坐席和客户都参与的情况下才会生成录音。</p>
     * 示例值：60
     */
    @JsonProperty("duration")
    private Integer duration;

    /**
     * 坐席 ID 列表（逗号分隔）。
     * 示例值：agent@report-test-2
     */
    @JsonProperty("agentIds")
    private String agentIds;

    /**
     * 文件名称。
     * 示例值：job-d0103c3e-db21-4075-9292-f88b1f978b24.wav
     */
    @JsonProperty("fileName")
    private String fileName;

    /**
     * 下载地址（OSS 下载链接）。
     * <p><b>注意：有过期时间，需及时下载。</b></p>
     * 示例值：https://***.oss-cn-shanghai.aliyuncs.com/ccc-record-mixed/...
     */
    @JsonProperty("downloadURL")
    private String downloadURL;

    /**
     * 话务 ID（即 jobId）。
     * <p>对应我方 {@code work_order.conversation_id} 字段。</p>
     * 示例值：job-d0103c3e-db21-4075-9292-f88b1f978b24
     */
    @JsonProperty("contactId")
    private String contactId;
}
