package cn.edu.xmu.javaee.logdemo.core.model;

import org.springframework.http.HttpStatus;

/**
 * 返回码，沿用课程仓库 core 模块 ReturnNo 的编号和含义，只保留本实验用到的部分。
 * 每个返回码同时决定 HTTP 状态码，两种实现因此返回完全相同的状态码和响应体。
 */
public enum ReturnNo {
    OK(0, "成功", HttpStatus.OK),
    CREATED(1, "创建成功", HttpStatus.CREATED),
    INTERNAL_SERVER_ERR(2, "服务器内部错误", HttpStatus.INTERNAL_SERVER_ERROR),
    FIELD_NOTVALID(3, "%s字段不合法", HttpStatus.BAD_REQUEST);

    private final int errNo;
    private final String message;
    private final HttpStatus httpStatus;

    ReturnNo(int errNo, String message, HttpStatus httpStatus) {
        this.errNo = errNo;
        this.message = message;
        this.httpStatus = httpStatus;
    }

    public int getErrNo() {
        return errNo;
    }

    public String getMessage() {
        return message;
    }

    public HttpStatus getHttpStatus() {
        return httpStatus;
    }
}
