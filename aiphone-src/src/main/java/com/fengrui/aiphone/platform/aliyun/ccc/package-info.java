/**
 * 阿里云云联络中心（CCC）对接模块。
 *
 * <p>CCC 是业务平台，负责管理整个客服系统的运转（坐席状态、通话、外呼、转接等）。
 * 包含三个子包：
 * <ul>
 *   <li>{@code callback} - 接收 CCC 推送的回调事件（通话状态、转人工、录音完成等）</li>
 *   <li>{@code client} - 主动调用 CCC API（SignInGroup/SignOutGroup、外呼、转接等）+ 扩展点接口</li>
 *   <li>{@code config} - CCC 连接配置（InstanceId、Region、AccessKey 等）</li>
 * </ul>
 *
 * <p>回调入口路径：{@code /api/aliyun/ccc/callback}</p>
 *
 * <p>对接资料待用户提供（详见 docs/旧参考开发日志.md 末尾「下阶段对接所需资料」）。</p>
 */
package com.fengrui.aiphone.platform.aliyun.ccc;
