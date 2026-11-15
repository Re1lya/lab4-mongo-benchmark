package cn.edu.xmu.javaee.logdemo.core.service;

import cn.edu.xmu.javaee.logdemo.core.controller.vo.LogVo;
import cn.edu.xmu.javaee.logdemo.core.exception.BusinessException;
import cn.edu.xmu.javaee.logdemo.core.model.LogLevel;
import cn.edu.xmu.javaee.logdemo.core.model.LogQuery;
import cn.edu.xmu.javaee.logdemo.core.model.LogRecord;
import cn.edu.xmu.javaee.logdemo.core.model.PageDto;
import cn.edu.xmu.javaee.logdemo.core.model.ReturnNo;
import cn.edu.xmu.javaee.logdemo.core.store.LogStore;
import cn.edu.xmu.javaee.logdemo.core.util.Ulid;
import cn.edu.xmu.javaee.logdemo.core.validation.IpAddress;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * 日志业务逻辑，两种实现共用。这里统一完成：
 * 生成 ULID、补全 createdAt/clientIp、时间统一为 UTC 毫秒精度、查询参数校验。
 * 持久化细节全部交给 {@link LogStore}。
 */
@Service
public class LogService {

    /** 不传 from/to 时的默认范围（相当于不限时间）。 */
    public static final Instant MIN_TIME = Instant.parse("1970-01-01T00:00:00Z");
    public static final Instant MAX_TIME = Instant.parse("9999-12-31T23:59:59.999Z");

    public static final int DEFAULT_PAGE_SIZE = 20;
    public static final int MAX_PAGE_SIZE = 100;
    /** 限制页码，避免深分页（OFFSET 很大）拖垮数据库。 */
    public static final int MAX_PAGE = 10_000;

    private static final Set<String> LEVELS = Arrays.stream(LogLevel.values())
            .map(Enum::name).collect(Collectors.toUnmodifiableSet());

    private final LogStore store;

    public LogService(LogStore store) {
        this.store = store;
    }

    public LogRecord create(LogVo vo, String remoteAddr) {
        // BSON Date 只有毫秒精度，MySQL DATETIME(6) 有微秒精度；
        // 统一截断到毫秒，保证两种数据库保存的时间完全相同。
        Instant createdAt = (vo.createdAt() == null ? Instant.now() : vo.createdAt())
                .truncatedTo(ChronoUnit.MILLIS);
        if (createdAt.isBefore(MIN_TIME) || createdAt.isAfter(MAX_TIME)) {
            throw new BusinessException(ReturnNo.FIELD_NOTVALID, "createdAt超出允许范围");
        }
        String clientIp = vo.clientIp();
        if (clientIp == null && remoteAddr != null && IpAddress.Validator.isIpAddress(remoteAddr)) {
            clientIp = remoteAddr;
        }
        LogRecord log = new LogRecord(Ulid.next(), vo.traceId(), vo.level(), vo.source(),
                vo.message(), clientIp, createdAt);
        return store.insert(log);
    }

    public PageDto<LogRecord> query(String level, String from, String to, int page, int size) {
        String lv = (level == null || level.isBlank()) ? null : level;
        if (lv != null && !LEVELS.contains(lv)) {
            throw new BusinessException(ReturnNo.FIELD_NOTVALID, "level只能是TRACE/DEBUG/INFO/WARN/ERROR");
        }
        Instant fromTime = (from == null || from.isBlank()) ? MIN_TIME : parseTime("from", from);
        Instant toTime = (to == null || to.isBlank()) ? MAX_TIME : parseTime("to", to);
        if (!fromTime.isBefore(toTime)) {
            throw new BusinessException(ReturnNo.FIELD_NOTVALID, "from必须早于to");
        }
        if (page < 1 || page > MAX_PAGE) {
            throw new BusinessException(ReturnNo.FIELD_NOTVALID, "page必须在1到" + MAX_PAGE + "之间");
        }
        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new BusinessException(ReturnNo.FIELD_NOTVALID, "size必须在1到" + MAX_PAGE_SIZE + "之间");
        }
        List<LogRecord> list = store.find(new LogQuery(lv, fromTime, toTime, page, size));
        return new PageDto<>(list, page, size);
    }

    /** 接受 ISO-8601 时间（2026-11-01T00:00:00Z 或 2026-11-01T08:00:00+08:00），换算为 UTC。 */
    static Instant parseTime(String name, String text) {
        // URL 中未编码的 “+” 会变成空格，这里还原
        String t = text.trim().replace(' ', '+');
        try {
            return OffsetDateTime.parse(t).toInstant();
        } catch (DateTimeParseException e) {
            throw new BusinessException(ReturnNo.FIELD_NOTVALID,
                    name + "必须是ISO-8601时间，例如2026-11-01T00:00:00Z");
        }
    }
}
