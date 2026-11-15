package cn.edu.xmu.javaee.logdemo.jpa;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * 日志服务 MySQL 版。
 * 组件扫描覆盖共用的 core 包；JPA 实体和 Repository 仍只在本包（自动配置包）中扫描。
 */
@SpringBootApplication(scanBasePackages = "cn.edu.xmu.javaee.logdemo")
public class LogJpaApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogJpaApplication.class, args);
    }
}
