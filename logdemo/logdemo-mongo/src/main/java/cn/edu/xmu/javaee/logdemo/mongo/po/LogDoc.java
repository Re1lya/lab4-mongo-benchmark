package cn.edu.xmu.javaee.logdemo.mongo.po;

import cn.edu.xmu.javaee.logdemo.core.model.LogRecord;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

import java.time.Instant;

/**
 * MongoDB 集合 log_record 中的文档（集合和索引见 db/mongo/01-init.js）。
 * <pre>
 * { _id: "01JD...(ULID)", traceId: "...", level: "INFO", source: "...",
 *   message: "...", clientIp: "...", createdAt: ISODate("2026-11-15T08:00:00.123Z") }
 * </pre>
 * id 用 ULID 字符串直接作为 _id（FieldType.STRING：不转换成 ObjectId）；
 * Instant 映射为 BSON Date（UTC，毫秒精度）；值为 null 的字段不写入文档。
 */
@Document(collection = "log_record")
public class LogDoc {

    @MongoId(FieldType.STRING)
    private String id;

    private String traceId;

    private String level;

    private String source;

    private String message;

    private String clientIp;

    private Instant createdAt;

    protected LogDoc() {
        // Spring Data 映射需要无参构造
    }

    public static LogDoc from(LogRecord r) {
        LogDoc doc = new LogDoc();
        doc.id = r.id();
        doc.traceId = r.traceId();
        doc.level = r.level();
        doc.source = r.source();
        doc.message = r.message();
        doc.clientIp = r.clientIp();
        doc.createdAt = r.createdAt();
        return doc;
    }

    public LogRecord toRecord() {
        return new LogRecord(id, traceId, level, source, message, clientIp, createdAt);
    }

    public String getId() {
        return id;
    }
}
