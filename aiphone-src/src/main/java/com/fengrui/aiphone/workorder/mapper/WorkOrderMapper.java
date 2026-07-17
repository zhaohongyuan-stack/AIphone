package com.fengrui.aiphone.workorder.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.fengrui.aiphone.workorder.entity.WorkOrder;
import org.apache.ibatis.annotations.Mapper;

/**
 * 工单 Mapper。
 */
@Mapper
public interface WorkOrderMapper extends BaseMapper<WorkOrder> {
}
