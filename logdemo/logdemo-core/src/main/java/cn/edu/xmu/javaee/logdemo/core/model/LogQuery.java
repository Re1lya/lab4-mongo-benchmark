package cn.edu.xmu.javaee.logdemo.core.model;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

import java.time.Instant;

/**
 * 分页查询条件：level 可为空（不按级别过滤），时间范围为 [from, to)。
 * page 从 1 开始，与课程仓库其他接口一致。
 */
public record LogQuery(String level, Instant from, Instant to, int page, int size) {

    /** 结果按产生时间倒序；时间相同时按 id 倒序，保证翻页顺序稳定。 */
    public static final Sort NEWEST_FIRST = Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"));

    public Pageable pageable() {
        return PageRequest.of(page - 1, size, NEWEST_FIRST);
    }
}
