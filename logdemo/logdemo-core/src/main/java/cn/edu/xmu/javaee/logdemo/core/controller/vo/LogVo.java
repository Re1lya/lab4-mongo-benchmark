package cn.edu.xmu.javaee.logdemo.core.controller.vo;

import cn.edu.xmu.javaee.logdemo.core.model.LogLevel;
import cn.edu.xmu.javaee.logdemo.core.validation.IpAddress;
import cn.edu.xmu.javaee.logdemo.core.validation.MaxCodePoints;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.Instant;

/**
 * POST /api/logs 的请求体。id 由服务端生成（ULID），请求中不需要也不接受。
 * createdAt 可省略，省略时取服务器当前时间；带时区偏移的时间会换算成 UTC。
 */
public record LogVo(
        @Size(max = 64, message = "traceId长度不能超过64")
        String traceId,

        @NotBlank(message = "level不能为空")
        @Pattern(regexp = LogLevel.PATTERN, message = "level只能是TRACE/DEBUG/INFO/WARN/ERROR")
        String level,

        @NotBlank(message = "source不能为空")
        @MaxCodePoints(value = 128, message = "source长度不能超过128个字符")
        String source,

        @NotBlank(message = "message不能为空")
        @MaxCodePoints(value = 4096, message = "message长度不能超过4096个字符")
        String message,

        @IpAddress(message = "clientIp不是合法的IPv4或IPv6地址")
        String clientIp,

        Instant createdAt) {
}
