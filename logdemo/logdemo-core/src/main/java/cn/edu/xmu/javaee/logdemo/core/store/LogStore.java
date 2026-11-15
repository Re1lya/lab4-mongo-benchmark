package cn.edu.xmu.javaee.logdemo.core.store;

import cn.edu.xmu.javaee.logdemo.core.model.LogQuery;
import cn.edu.xmu.javaee.logdemo.core.model.LogRecord;

import java.util.List;

/**
 * 持久层接口：两种实现的唯一差别。
 * logdemo-jpa 用 Spring Data JPA 访问 MySQL，logdemo-mongo 用 Spring Data MongoDB 访问 MongoDB。
 */
public interface LogStore {

    /** 单条写入，返回已保存的日志。 */
    LogRecord insert(LogRecord log);

    /** 按级别和时间范围分页查询，按 createdAt、id 倒序。 */
    List<LogRecord> find(LogQuery query);

    /** 实现名称（jpa 或 mongo），用于监控标签和健康检查。 */
    String implementation();
}
