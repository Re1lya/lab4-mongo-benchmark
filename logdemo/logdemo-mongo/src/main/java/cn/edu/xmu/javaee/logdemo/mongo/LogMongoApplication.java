package cn.edu.xmu.javaee.logdemo.mongo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 日志服务 MongoDB 版。
 * 组件扫描覆盖共用的 core 包；Mongo 文档和 Repository 仍只在本包（自动配置包）中扫描。
 */
@SpringBootApplication(scanBasePackages = "cn.edu.xmu.javaee.logdemo")
public class LogMongoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogMongoApplication.class, args);
    }
}
