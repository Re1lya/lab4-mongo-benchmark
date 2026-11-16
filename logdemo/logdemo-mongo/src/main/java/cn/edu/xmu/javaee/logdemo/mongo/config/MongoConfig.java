package cn.edu.xmu.javaee.logdemo.mongo.config;

import com.mongodb.WriteConcern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.mongo.MongoClientSettingsBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.core.convert.DefaultDbRefResolver;
import org.springframework.data.mongodb.core.convert.DefaultMongoTypeMapper;
import org.springframework.data.mongodb.core.convert.MappingMongoConverter;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

import java.util.concurrent.TimeUnit;

/**
 * MongoDB 客户端配置。
 */
@Configuration
public class MongoConfig {

    private static final Logger logger = LoggerFactory.getLogger(MongoConfig.class);

    /**
     * 连接池与 MySQL 版的 HikariCP 设置相同：最大连接数、最小连接数、取连接最长等待时间。
     * （驱动默认 maxPoolSize=100、等待 2 分钟；HikariCP 默认 10 个连接、等待 30 秒，差别很大。）
     * <p>
     * 写关注：默认 w:1（单机 MongoDB 的默认值，写入在内存中生效即确认，日志约每 100ms 批量刷盘）。
     * logdemo.mongo.journal=true 时改为 w:1 + j:true：等日志落盘后才确认，持久性与 MySQL
     * （innodb_flush_log_at_trx_commit=1）对齐，用于“同等持久性”下的写入对比。
     * 部署时用环境变量 LOGDEMO_MONGO_JOURNAL=true 打开。
     */
    @Bean
    public MongoClientSettingsBuilderCustomizer poolSettings(
            @Value("${logdemo.pool.max-size}") int maxSize,
            @Value("${logdemo.pool.wait-timeout-ms}") long waitTimeoutMs,
            @Value("${logdemo.mongo.journal:false}") boolean journal) {
        WriteConcern writeConcern = journal ? WriteConcern.W1.withJournal(true) : WriteConcern.W1;
        logger.info("logdemo-mongo settings: pool max-size={} wait-timeout={}ms, writeConcern={}",
                maxSize, waitTimeoutMs, writeConcern.asDocument().toJson());
        return builder -> builder
                .writeConcern(writeConcern)
                .applyToConnectionPoolSettings(pool -> pool
                        .maxSize(maxSize)
                        .minSize(maxSize)
                        .maxWaitTime(waitTimeoutMs, TimeUnit.MILLISECONDS));
    }

    /**
     * 不在每个文档里写 "_class" 字段。Spring Data MongoDB 默认会写入实体类全名，
     * 每条日志多存几十字节；本实验集合只存一种文档，不需要它，去掉后两边保存的字段一致。
     */
    @Bean
    public MappingMongoConverter mappingMongoConverter(MongoDatabaseFactory factory,
                                                       MongoMappingContext context,
                                                       MongoCustomConversions conversions) {
        MappingMongoConverter converter = new MappingMongoConverter(new DefaultDbRefResolver(factory), context);
        converter.setCustomConversions(conversions);
        converter.setTypeMapper(new DefaultMongoTypeMapper(null));
        return converter;
    }
}
