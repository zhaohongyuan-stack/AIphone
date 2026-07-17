package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC Ringing（振铃）事件数据。
 *
 * <p>触发场景：通话通道进入振铃状态。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>我方处理：记录振铃时间，可暂存，待 {@link EstablishedEventData} 时写入
 * {@code work_order.call_start_time}。</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class RingingEventData extends CccCallEventData {

    /**
     * 拨号场景。
     * 可选值：BLIND_TRANSFER（直接转接）/ATTENDED_TRANSFER（咨询转接）/CONSULTED（咨询）/
     * MONITORING（监听中）/COACHING（辅导中）/INTERCEPTING（强拆中）/INTERCEPTED（强拆完成）/
     * BARGING（强插中）/CONFERENCE（会议）
     */
    @JsonProperty("scenario")
    private String scenario;

    /**
     * 目的方（转接场景）。
     * 示例值：80002301
     */
    @JsonProperty("destination")
    private String destination;

    /**
     * 业务标识（当外部调度应用发起主动调度时传入的唯一业务 ID）。
     * 示例值：bizId=j123949
     */
    @JsonProperty("tags")
    private String tags;
}
