package cn.edu.xmu.javaee.logdemo.jpa;

import cn.edu.xmu.javaee.logdemo.core.model.LogQuery;
import cn.edu.xmu.javaee.logdemo.core.model.LogRecord;
import cn.edu.xmu.javaee.logdemo.core.store.LogStore;
import cn.edu.xmu.javaee.logdemo.jpa.mapper.LogPoMapper;
import cn.edu.xmu.javaee.logdemo.jpa.po.LogPo;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * LogStore 的 JPA/MySQL 实现。
 * save() 自带事务：每次写入是一个独立事务，提交时 InnoDB 按 innodb_flush_log_at_trx_commit 刷 redo log。
 */
@Repository
public class JpaLogStore implements LogStore {

    private final LogPoMapper mapper;

    public JpaLogStore(LogPoMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public LogRecord insert(LogRecord log) {
        mapper.save(LogPo.from(log));
        return log;
    }

    @Override
    public List<LogRecord> find(LogQuery q) {
        List<LogPo> rows = q.level() == null
                ? mapper.findPageAllLevels(q.from(), q.to(), q.pageable())
                : mapper.findPage(q.level(), q.from(), q.to(), q.pageable());
        return rows.stream().map(LogPo::toRecord).toList();
    }

    @Override
    public String implementation() {
        return "jpa";
    }
}
