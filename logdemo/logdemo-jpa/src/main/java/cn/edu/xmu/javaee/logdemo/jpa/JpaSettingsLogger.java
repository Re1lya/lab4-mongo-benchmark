package cn.edu.xmu.javaee.logdemo.jpa;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * 启动时打印实际生效的连接池设置，部署时用环境变量 LOGDEMO_POOL_MAXSIZE 等改动后，可在日志中核对。
 */
@Component
public class JpaSettingsLogger implements ApplicationRunner {

    private static final Logger logger = LoggerFactory.getLogger(JpaSettingsLogger.class);

    @Value("${spring.datasource.hikari.maximum-pool-size}")
    private int maxPoolSize;

    @Value("${spring.datasource.hikari.connection-timeout}")
    private long connectionTimeout;

    @Override
    public void run(ApplicationArguments args) {
        logger.info("logdemo-jpa settings: pool max-size={} wait-timeout={}ms", maxPoolSize, connectionTimeout);
    }
}
