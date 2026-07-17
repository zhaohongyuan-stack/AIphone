/**
 * CCC 模块 - 主动调用客户端层。
 *
 * <p>包含两部分：
 * <ul>
 *   <li>扩展点接口（如 {@code CccAgentClient}）：定义坐席上下线等行为契约</li>
 *   <li>真实实现（待对接 CCC 时落地，使用 @ConditionalOnMissingBean 自动替换空实现）</li>
 * </ul>
 *
 * <p>需覆盖的主动调用接口（至少）：
 * SignInGroup/SignOutGroup（坐席上下线）、外呼、转接、强插/监听/强拆、查询坐席状态、查询排队情况。</p>
 */
package com.fengrui.aiphone.platform.aliyun.ccc.client;
