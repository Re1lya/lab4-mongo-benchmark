package cn.edu.xmu.javaee.logdemo.core.model;

import java.util.List;

/**
 * 分页结果，字段与课程仓库 PageDto 相同（list、page、pageSize）。
 * 不返回总数：总数需要额外的 count 查询，会让读接口的耗时主要变成计数耗时。
 */
public record PageDto<T>(List<T> list, int page, int pageSize) {
}
