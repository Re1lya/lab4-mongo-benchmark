package cn.edu.xmu.javaee.logdemo.core.controller;

import cn.edu.xmu.javaee.logdemo.core.exception.BusinessException;
import cn.edu.xmu.javaee.logdemo.core.model.ReturnNo;
import cn.edu.xmu.javaee.logdemo.core.model.ReturnObject;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

import java.util.stream.Collectors;

/**
 * 把异常转换为统一响应体：参数错误 400（errno=3），其他运行时错误 500（errno=2）。
 * 404/405/415 等框架异常不是 RuntimeException，仍由 Spring 默认处理。
 */
@RestControllerAdvice
public class ControllerAdvice {

    private static final Logger logger = LoggerFactory.getLogger(ControllerAdvice.class);

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ReturnObject> business(BusinessException e) {
        return build(e.getErrno(), e.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ReturnObject> invalidBody(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .sorted()
                .collect(Collectors.joining(";"));
        return build(ReturnNo.FIELD_NOTVALID, msg);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ReturnObject> unreadable(HttpMessageNotReadableException e) {
        return build(ReturnNo.FIELD_NOTVALID, "请求体不是合法的JSON日志对象");
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ReturnObject> typeMismatch(MethodArgumentTypeMismatchException e) {
        return build(ReturnNo.FIELD_NOTVALID, e.getName() + "格式不正确");
    }

    @ExceptionHandler(RuntimeException.class)
    public ResponseEntity<ReturnObject> internal(RuntimeException e) {
        // 压力测试时错误可能很多：只记一行，堆栈放到 DEBUG，避免日志本身拖慢服务
        logger.warn("request failed: {}", e.toString());
        logger.debug("request failed", e);
        return build(ReturnNo.INTERNAL_SERVER_ERR, ReturnNo.INTERNAL_SERVER_ERR.getMessage());
    }

    private static ResponseEntity<ReturnObject> build(ReturnNo code, String message) {
        return ResponseEntity.status(code.getHttpStatus()).body(new ReturnObject(code, message, null));
    }
}
