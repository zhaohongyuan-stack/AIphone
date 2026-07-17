package com.fengrui.aiphone;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * AIPhone 智能客服平台启动类。
 *
 * <p>@MapperScan 使用 **.mapper 通配，适配模块化包结构
 * （workorder.mapper / agent.mapper / dialogue.mapper 等业务模块各自的 mapper 包）。</p>
 */
@SpringBootApplication
@MapperScan("com.fengrui.aiphone.**.mapper")
public class AiPhoneApplication {

    public static void main(String[] args) {
        SpringApplication.run(AiPhoneApplication.class, args);
    }

}
