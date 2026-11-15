package cn.edu.xmu.javaee.logdemo.jpa.mapper;

import cn.edu.xmu.javaee.logdemo.jpa.po.LogPo;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;

/**
 * Spring Data JPA Repository。返回 List 而不是 Page：Pageable 只生成 ORDER BY ... LIMIT ?,?，
 * 不会额外执行 count 查询。生成的 SQL 形如：
 * <pre>
 * select ... from log_record where level=? and created_at>=? and created_at<?
 * order by created_at desc, id desc limit ?, ?
 * </pre>
 * 对应索引 idx_level_created(level, created_at, id)。
 */
public interface LogPoMapper extends JpaRepository<LogPo, String> {

    @Query("select l from LogPo l where l.level = :level and l.createdAt >= :from and l.createdAt < :to")
    List<LogPo> findPage(@Param("level") String level, @Param("from") Instant from,
                         @Param("to") Instant to, Pageable pageable);

    @Query("select l from LogPo l where l.createdAt >= :from and l.createdAt < :to")
    List<LogPo> findPageAllLevels(@Param("from") Instant from, @Param("to") Instant to, Pageable pageable);
}
