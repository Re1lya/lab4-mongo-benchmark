package cn.edu.xmu.javaee.logdemo.mongo;

import cn.edu.xmu.javaee.logdemo.core.model.LogQuery;
import cn.edu.xmu.javaee.logdemo.core.model.LogRecord;
import cn.edu.xmu.javaee.logdemo.core.store.LogStore;
import cn.edu.xmu.javaee.logdemo.mongo.mapper.LogDocMapper;
import cn.edu.xmu.javaee.logdemo.mongo.po.LogDoc;
import org.springframework.stereotype.Repository;

import java.util.List;

/**
 * LogStore 的 Spring Data MongoDB 实现。
 * insert() 直接执行 insertOne；不用 save()，因为 save() 是“按 _id 替换，不存在则插入”的 upsert。
 */
@Repository
public class MongoLogStore implements LogStore {

    private final LogDocMapper mapper;

    public MongoLogStore(LogDocMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public LogRecord insert(LogRecord log) {
        mapper.insert(LogDoc.from(log));
        return log;
    }

    @Override
    public List<LogRecord> find(LogQuery q) {
        List<LogDoc> docs = q.level() == null
                ? mapper.findPageAllLevels(q.from(), q.to(), q.pageable())
                : mapper.findPage(q.level(), q.from(), q.to(), q.pageable());
        return docs.stream().map(LogDoc::toRecord).toList();
    }

    @Override
    public String implementation() {
        return "mongo";
    }
}
