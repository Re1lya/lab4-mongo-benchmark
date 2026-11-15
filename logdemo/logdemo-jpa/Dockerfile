# 与课程仓库相同的基础镜像（华为云 SWR 上的 OpenJDK 21）
FROM swr.cn-north-4.myhuaweicloud.com/oomall-javaee/openjdk:21-alpine
WORKDIR /app
ARG JAR_FILE=target/logdemo-jpa.jar
COPY ${JAR_FILE} /app/app.jar
EXPOSE 8080
# JVM 参数由部署文件中的 JAVA_TOOL_OPTIONS 提供，数据库连接由私密配置文件提供
ENTRYPOINT ["java", "-jar", "app.jar"]
