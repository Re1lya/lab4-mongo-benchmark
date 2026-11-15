package cn.edu.xmu.javaee.logdemo.core.model;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.time.Instant;

/**
 * 日志业务对象，也是接口返回的日志格式。
 * 两种实现只在持久层把它转换成各自的 PO（JPA 实体 / Mongo 文档），业务层和接口层只认识这个类。
 *
 * @param id        业务主键，26 位 ULID
 * @param traceId   链路追踪标识，可为空
 * @param level     TRACE/DEBUG/INFO/WARN/ERROR
 * @param source    服务名或模块名
 * @param message   日志正文，不超过 4096 个字符
 * @param clientIp  IPv4 或 IPv6 文本
 * @param createdAt 日志产生时间（UTC，毫秒精度），JSON 中形如 2026-11-15T08:00:00.123Z
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record LogRecord(String id, String traceId, String level, String source,
                        String message, String clientIp, Instant createdAt) {
}
