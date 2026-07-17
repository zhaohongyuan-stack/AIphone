package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC Released（挂机）事件数据。
 *
 * <p>触发场景：通话通道进入挂机状态（通话结束）。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>我方处理：更新 {@code work_order.call_end_time}（通话结束时间）、
 * {@code order_status} 为已办结/主动挂断（根据 {@link #releaseInitiator} 判断）。
 * 若电话未接通，记录 {@link #earlyMediaState}（早媒体未接通原因）。</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class ReleasedEventData extends CccCallEventData {

    /**
     * 挂断方。
     * <p>标识是谁首先挂断了电话，可能是号码或 agentId。</p>
     * 示例值：05719213xxxx 或 agent@report-test-2
     */
    @JsonProperty("releaseInitiator")
    private String releaseInitiator;

    /**
     * 挂断原因（来源于 SIP 信令）。
     * <p>如果不熟悉 SIP 返回码，可以咨询云呼售后技术支持。</p>
     * 示例值：200 - Okay / 480 - Temporarily Unavailable
     */
    @JsonProperty("releaseReason")
    private String releaseReason;

    /**
     * 电话未接通时，根据早媒体判断的未接通原因状态码。
     * <p>仅电话未接通时有值。</p>
     * 可选值：NoAnswer（无人接听）/OutOfService（停机）/NotExist（空号）/
     * Restricted（呼叫受限）/Busy（占线）/NotConnected（无法接通）/PowerOff（关机）
     */
    @JsonProperty("earlyMediaState")
    private String earlyMediaState;

    /**
     * 电话未接通时，识别出来的早媒体的内容。
     * 示例值：Busy 0.9987
     */
    @JsonProperty("earlyMediaText")
    private String earlyMediaText;

    /**
     * 拨号场景。
     * 可选值：BLIND_TRANSFER（直接转接）/ATTENDED_TRANSFER（咨询转接）/CONSULTED（咨询）/
     * MONITORING（监听中）/COACHING（辅导中）/INTERCEPTING（强拆中）/INTERCEPTED（强拆完成）/
     * BARGING（强插中）/CONFERENCE（会议）
     */
    @JsonProperty("scenario")
    private String scenario;

    /**
     * 业务标识（当外部调度应用发起主动调度时传入的唯一业务 ID）。
     * 示例值：bizId=j123949
     */
    @JsonProperty("tags")
    private String tags;
}
