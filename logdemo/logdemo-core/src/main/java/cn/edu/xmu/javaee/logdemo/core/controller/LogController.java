package cn.edu.xmu.javaee.logdemo.core.controller;

import cn.edu.xmu.javaee.logdemo.core.controller.vo.LogVo;
import cn.edu.xmu.javaee.logdemo.core.model.LogRecord;
import cn.edu.xmu.javaee.logdemo.core.model.PageDto;
import cn.edu.xmu.javaee.logdemo.core.model.ReturnNo;
import cn.edu.xmu.javaee.logdemo.core.model.ReturnObject;
import cn.edu.xmu.javaee.logdemo.core.service.LogService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 统一 REST 接口（表 3）。两种实现共用同一个 Controller，
 * 因此 JMeter 只需替换主机和端口，请求体、断言和线程组都不用改。
 */
@RestController
@RequestMapping(value = "/api/logs", produces = "application/json;charset=UTF-8")
public class LogController {

    private final LogService logService;

    public LogController(LogService logService) {
        this.logService = logService;
    }

    /** 单条写入：成功返回 HTTP 201，errno=1（创建成功），data 为保存后的日志。 */
    @PostMapping
    public ResponseEntity<ReturnObject> create(@Valid @RequestBody LogVo vo, HttpServletRequest request) {
        LogRecord saved = logService.create(vo, request.getRemoteAddr());
        return ResponseEntity.status(ReturnNo.CREATED.getHttpStatus())
                .body(new ReturnObject(ReturnNo.CREATED, saved));
    }

    /** 按级别和时间范围 [from, to) 分页查询：成功返回 HTTP 200，errno=0。 */
    @GetMapping
    public ReturnObject query(@RequestParam(required = false) String level,
                              @RequestParam(required = false) String from,
                              @RequestParam(required = false) String to,
                              @RequestParam(defaultValue = "1") int page,
                              @RequestParam(defaultValue = "" + LogService.DEFAULT_PAGE_SIZE) int size) {
        PageDto<LogRecord> result = logService.query(level, from, to, page, size);
        return new ReturnObject(result);
    }
}
