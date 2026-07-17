package com.fengrui.aiphone.platform.aliyun.ccc.callback.dto;

/**
 * CCC 事件类型枚举。
 *
 * <p>对应阿里云云联络中心（CCC）的所有回调事件类型，共 50 个事件。
 * 文档来源：https://help.aliyun.com/zh/ccs/use-cases/event-notification-formats</p>
 *
 * <p>本阶段仅 {@link #Ringing} / {@link #Established} / {@link #Released} /
 * {@link #RecordingReady} 4 个事件有专用 DTO，其余事件用基类接收 + 日志打印。</p>
 */
public enum CccEventType {

    // ==================== 一、坐席事件（9个）====================

    /** 坐席签入：触发场景-坐席单击「上线」并签入技能组 */
    AgentCheckIn,
    /** 坐席就绪：触发场景-坐席进入就绪状态 */
    AgentReady,
    /** 坐席拨号：触发场景-坐席进入外呼状态 */
    AgentDialing,
    /** 坐席振铃：触发场景-坐席进入振铃状态（有来电或转接来电） */
    AgentRinging,
    /** 坐席通话：触发场景-坐席进入通话状态（通话建立） */
    AgentTalk,
    /** 坐席挂机：触发场景-坐席主动挂机或被动挂机（通话结束） */
    AgentRelease,
    /** 坐席小休：触发场景-坐席进入小休状态（单击「小休」） */
    AgentBreak,
    /** 坐席签出：触发场景-坐席单击「下线」 */
    AgentCheckOut,
    /** 坐席振铃超时：触发场景-坐席久振未接（超时时长根据配置决定） */
    AgentRingingTimeout,

    // ==================== 二、话务事件（23个）====================

    // -- 通话通道事件 --
    /** 拨号：触发场景-通道进入拨号状态 */
    Dialing,
    /** 振铃：触发场景-通道进入振铃状态（呼叫振铃）→ 更新 work_order.call_start_time */
    Ringing,
    /** 通话建立：触发场景-通道进入通话状态（通话建立）→ 更新 work_order.call_start_time */
    Established,
    /** 挂机：触发场景-通道进入挂机状态（通话挂机）→ 更新 work_order.call_end_time/order_status */
    Released,
    /** 通话保持：触发场景-通道进入保持状态（单击「通话保持」） */
    Held,
    /** 通话取回：触发场景-取消通道保持状态（单击「通话取回」） */
    Retrieved,
    /** 静音：触发场景-通道进入静音状态（单击「静音」） */
    Muted,
    /** 取消静音：触发场景-取消通道静音（单击「取消静音」） */
    Unmuted,

    // -- 话务场景事件 --
    /** 直接转接：触发场景-坐席进行直接转接操作 */
    BlindTransfer,
    /** 咨询转接：触发场景-坐席进行转移通话操作 */
    AttendedTransfer,
    /** 开始会议：触发场景-发起会议 */
    StartConference,
    /** 结束会议：触发场景-结束会议 */
    StopConference,

    // -- IVR 事件 --
    /** 进入IVR：触发场景-客户发起的呼叫进入IVR */
    Route2IVR,
    /** 放弃：触发场景-客户在IVR交互过程中放弃 */
    Abandoned,
    /** 进入队列：触发场景-客户进入IVR转人工队列 */
    Enqueue,
    /** 排队超时：触发场景-排队超过指定时间 */
    QueueingTimeout,
    /** 排队溢出：触发场景-排队人数超过上限 */
    QueueingOverflow,
    /** 排队终止：触发场景-从排队队列中移除 */
    QueueingCancelled,
    /** 重新排队：触发场景-从一个队列转移到另一个 */
    QueueingRerouted,
    /** 排队失败：触发场景-不能进入指定队列 */
    QueueingFailure,
    /** 调度失败：触发场景-调度指令执行失败 */
    DispatchingFailure,
    /** 分配坐席失败：触发场景-坐席状态异常无法分配 */
    AssignAgentFailure,
    /** 分配坐席：触发场景-通话成功分配到坐席 */
    AssignAgent,

    // -- 咨询转接专用事件 --
    /** 发起咨询：触发场景-发起咨询转接（类似AgentDialing） */
    InitiateConsultant,
    /** 开始咨询：触发场景-咨询接通（类似AgentTalk） */
    StartConsultant,
    /** 结束咨询：触发场景-咨询结束（类似AgentRelease） */
    StopConsultant,

    // ==================== 三、督导事件（6个）====================

    /** 开始监听：触发场景-督导开始监听坐席通话 */
    StartMonitor,
    /** 结束监听：触发场景-督导结束监听 */
    StopMonitor,
    /** 开始辅导：触发场景-督导开始辅导坐席 */
    StartCoach,
    /** 结束辅导：触发场景-督导结束辅导 */
    StopCoach,
    /** 强插：触发场景-督导强行插入通话 */
    BargeIn,
    /** 强拆：触发场景-督导强行拆线并接管通话 */
    Intercept,

    // ==================== 四、IVR轨迹事件（1个）====================

    /** IVR轨迹：触发场景-IVR 每个节点进入/离开时触发 */
    IvrTracking,

    // ==================== 五、实时流事件（2个）====================

    /** 文本流：触发场景-ASR 实时识别结果推送（CCC 自带 ASR） */
    TextStream,
    /** 媒体流：触发场景-媒体流推送（功能开发中） */
    MediaStream,

    // ==================== 六、预测式外呼事件（6个）====================

    /** 活动提交：触发场景-预测式外呼活动提交 */
    CampaignSubmitted,
    /** 活动暂停：触发场景-预测式外呼活动暂停 */
    CampaignPaused,
    /** 活动恢复：触发场景-预测式外呼活动恢复 */
    CampaignResumed,
    /** 活动终止：触发场景-预测式外呼活动终止 */
    CampaignAborted,
    /** 活动完成：触发场景-预测式外呼活动完成 */
    CampaignCompleted,
    /** 案件执行：触发场景-预测式外呼案件执行 */
    CaseAttempted,

    // ==================== 七、其他事件（5个）====================

    /** 满意度评价邀请：触发场景-坐席发起满意度评价邀请 */
    SatisfactionSurveyOffer,
    /** 满意度评价答复：触发场景-客户答复满意度评价 */
    SatisfactionSurveyResponse,
    /** 录音生成：触发场景-录音文件生成完成 → 可触发录音文件转写 */
    RecordingReady,
    /** 多轨录音生成：触发场景-多轨录音文件生成完成 */
    DualTrackRecordingReady,
    /** 通话详单生成：触发场景-通话详情单生成完成 */
    CDRReady
}
