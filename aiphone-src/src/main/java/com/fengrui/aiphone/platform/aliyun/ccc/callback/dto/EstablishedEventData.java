package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;

/**
 * CCC Established（通话建立）事件数据。
 *
 * <p>触发场景：通话通道进入通话状态（接通）。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>我方处理：更新 {@code work_order.call_start_time}（通话开始时间），
 * 更新 {@code order_status} 为进行中。</p>
 */
@Data
@EqualsAndHashCode(callSuper = true)
public class EstablishedEventData extends CccCallEventData {

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
