package cn.edu.xmu.javaee.logdemo.jpa.po;

import cn.edu.xmu.javaee.logdemo.core.model.LogRecord;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import org.springframework.data.domain.Persistable;

import java.time.Instant;

/**
 * MySQL 表 log_record 对应的 JPA 实体（表结构见 db/mysql/01-schema.sql）。
 * <p>
 * 实现 Persistable：主键 id 由程序预先赋值（ULID），Spring Data 的 save() 默认会把
 * “id 不为空”的实体当成已存在的对象，先 SELECT 再 merge。用 isNew() 告诉它这是新对象，
 * save() 就直接 persist，一次写入只执行一条 INSERT。
 */
@Entity
@Table(name = "log_record")
public class LogPo implements Persistable<String> {

    @Id
    @Column(name = "id", length = 26, nullable = false)
    private String id;

    @Column(name = "trace_id", length = 64)
    private String traceId;

    @Column(name = "level", length = 10, nullable = false)
    private String level;

    @Column(name = "source", length = 128, nullable = false)
    private String source;

    @Column(name = "message", length = 4096, nullable = false)
    private String message;

    @Column(name = "client_ip", length = 45)
    private String clientIp;

    /** DATETIME(6)，按 UTC 保存（hibernate.jdbc.time_zone=UTC）。 */
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Transient
    private boolean newEntity = true;

    protected LogPo() {
        // JPA 需要无参构造
    }

    public static LogPo from(LogRecord r) {
        LogPo po = new LogPo();
        po.id = r.id();
        po.traceId = r.traceId();
        po.level = r.level();
        po.source = r.source();
        po.message = r.message();
        po.clientIp = r.clientIp();
        po.createdAt = r.createdAt();
        return po;
    }

    public LogRecord toRecord() {
        return new LogRecord(id, traceId, level, source, message, clientIp, createdAt);
    }

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostLoad
    @PostPersist
    void markNotNew() {
        this.newEntity = false;
    }
}
