package cn.edu.xmu.javaee.logdemo.core.model;

/**
 * 日志级别。数据库中按字符串保存（MySQL VARCHAR(10)，MongoDB String）。
 */
public enum LogLevel {
    TRACE, DEBUG, INFO, WARN, ERROR;

    /** 接口参数和请求体里的级别必须匹配这个正则（大写）。 */
    public static final String PATTERN = "TRACE|DEBUG|INFO|WARN|ERROR";
}
