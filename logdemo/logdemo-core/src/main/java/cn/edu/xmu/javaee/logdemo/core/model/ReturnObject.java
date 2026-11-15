package cn.edu.xmu.javaee.logdemo.core.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 统一响应体 {"errno":..,"errmsg":..,"data":..}，格式与课程仓库的 ReturnObject 相同。
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ReturnObject {

    @JsonIgnore
    private final ReturnNo code;

    @JsonProperty("errmsg")
    private final String errMsg;

    @JsonProperty("data")
    private final Object data;

    public ReturnObject(Object data) {
        this(ReturnNo.OK, ReturnNo.OK.getMessage(), data);
    }

    public ReturnObject(ReturnNo code, Object data) {
        this(code, code.getMessage(), data);
    }

    public ReturnObject(ReturnNo code, String errMsg, Object data) {
        this.code = code;
        this.errMsg = errMsg;
        this.data = data;
    }

    @JsonProperty("errno")
    public int getErrno() {
        return code.getErrNo();
    }

    public ReturnNo getCode() {
        return code;
    }

    public String getErrMsg() {
        return errMsg;
    }

    public Object getData() {
        return data;
    }
}
