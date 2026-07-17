/**
 * CCC 模块 - 回调接收层。
 *
 * <p>接收 CCC 平台推送给我们的回调事件：
 * <ul>
 *   <li>通话状态变更（振铃/接听/挂断）→ 更新 work_order.call_start_time/call_end_time/order_status</li>
 *   <li>转人工请求 → 触发坐席分配</li>
 *   <li>录音文件生成完成 → 触发语音转写</li>
 *   <li>IVR 按键事件 → 用于分流决策</li>
 *   <li>坐席状态变更（CCC 侧主动变更时同步我方）</li>
 * </ul>
 *
 * <p>入口：{@code CccCallbackController}，路径 {@code /api/aliyun/ccc/callback}</p>
 */
package com.fengrui.aiphone.platform.aliyun.ccc.callback;
