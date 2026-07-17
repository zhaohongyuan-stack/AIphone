package com.fengrui.aiphone.agent.controller;

import com.fengrui.aiphone.agent.dto.req.AgentStatusUpdateReq;
import com.fengrui.aiphone.agent.service.AgentInfoService;
import com.fengrui.aiphone.agent.vo.AgentStatusUpdateVO;
import com.fengrui.aiphone.agent.vo.AgentVO;
import com.fengrui.aiphone.common.Result;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 坐席接口。
 */
@RestController
@RequestMapping("/api/agent")
public class AgentController {

    @Autowired
    private AgentInfoService agentInfoService;

    /** 坐席状态管理（DB + Redis + CCC） */
    @PutMapping("/status")
    public Result<AgentStatusUpdateVO> updateStatus(@Valid @RequestBody AgentStatusUpdateReq req) {
        return Result.success("状态更新成功", agentInfoService.updateStatus(req));
    }

    /** 查询全量坐席列表 */
    @GetMapping("/list")
    public Result<List<AgentVO>> list() {
        return Result.success(agentInfoService.listAgents());
    }
}
