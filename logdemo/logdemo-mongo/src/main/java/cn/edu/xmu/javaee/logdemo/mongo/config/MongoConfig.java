package cn.edu.xmu.javaee.logdemo.mongo.config;

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

    /**
     * 连接池与 MySQL 版的 HikariCP 设置相同：最大连接数、最小连接数、取连接最长等待时间。
     * （驱动默认 maxPoolSize=100、等待 2 分钟；HikariCP 默认 10 个连接、等待 30 秒，差别很大。）
     */
    @Bean
    public MongoClientSettingsBuilderCustomizer poolSettings(
            @Value("${logdemo.pool.max-size}") int maxSize,
            @Value("${logdemo.pool.wait-timeout-ms}") long waitTimeoutMs) {
        return builder -> builder.applyToConnectionPoolSettings(pool -> pool
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
