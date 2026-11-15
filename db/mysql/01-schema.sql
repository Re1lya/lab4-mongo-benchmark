-- 实验四 MySQL 初始化：库 lab4_log、表 log_record（字段与指导书表 2 一致）
-- 执行：mysql -uroot -p < 01-schema.sql   （可重复执行，已存在则跳过）

CREATE DATABASE IF NOT EXISTS lab4_log
  DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;

USE lab4_log;

CREATE TABLE IF NOT EXISTS log_record (
  -- ULID 只含 ASCII 字符：用 ascii_bin 保存，每个字符 1 字节，且按二进制比较 = 按时间排序。
  -- 主键会附在每个二级索引的叶子节点上，主键越短，二级索引越小。
  id         CHAR(26)      CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '业务主键（ULID）',
  trace_id   VARCHAR(64)   NULL     COMMENT '链路追踪标识，可为空',
  level      VARCHAR(10)   NOT NULL COMMENT 'TRACE/DEBUG/INFO/WARN/ERROR',
  source     VARCHAR(128)  NOT NULL COMMENT '服务名或模块名',
  message    VARCHAR(4096) NOT NULL COMMENT '日志正文（不超过 4096 个字符）',
  client_ip  VARCHAR(45)   NULL     COMMENT 'IPv4/IPv6',
  created_at DATETIME(6)   NOT NULL COMMENT '日志产生时间（UTC）',
  PRIMARY KEY (id),
  -- 按级别 + 时间范围分页查询：WHERE level=? AND created_at>=? AND created_at<? ORDER BY created_at DESC, id DESC
  KEY idx_level_created (level, created_at, id),
  -- 不指定级别、只按时间范围查询
  KEY idx_created (created_at, id),
  CONSTRAINT chk_log_level CHECK (level IN ('TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR'))
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci
  COMMENT = '实验四日志表';
