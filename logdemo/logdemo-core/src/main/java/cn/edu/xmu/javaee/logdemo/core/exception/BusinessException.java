package cn.edu.xmu.javaee.logdemo.core.exception;

import cn.edu.xmu.javaee.logdemo.core.model.ReturnNo;

/**
 * 业务异常：携带返回码，由 ControllerAdvice 转换成统一响应。
 */
public class BusinessException extends RuntimeException {

    private final ReturnNo errno;

    public BusinessException(ReturnNo errno, String message) {
        super(message);
        this.errno = errno;
    }

    public ReturnNo getErrno() {
        return errno;
    }
}
