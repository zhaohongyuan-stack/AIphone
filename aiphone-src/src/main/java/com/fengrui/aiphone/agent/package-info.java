/**
 * 业务模块：人工坐席（agent）。
 *
 * <p>负责人：我（后端开发者）。承载坐席状态管理、坐席分配等业务。
 * 内部按 entity/mapper/service/controller/dto/vo 分层。</p>
 *
 * <p>对接阿里云 CCC 平台的 SignInGroup/SignOutGroup 接口
 * （通过 platform.aliyun.ccc.client 扩展点）。</p>
 */
package com.fengrui.aiphone.agent;
