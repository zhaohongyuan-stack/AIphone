package com.fengrui.aiphone.workorder.vo;

import lombok.Data;

import java.util.List;

/**
 * 通用分页结果。
 */
@Data
public class PageResult<T> {

    private Long total;
    private Integer page;
    private Integer pageSize;
    private List<T> list;

    public static <T> PageResult<T> of(long total, int page, int pageSize, List<T> list) {
        PageResult<T> r = new PageResult<>();
        r.setTotal(total);
        r.setPage(page);
        r.setPageSize(pageSize);
        r.setList(list);
        return r;
    }
}
