package cn.edu.xmu.javaee.logdemo.core.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * 按“字符”（Unicode 码点）限制长度，与 MySQL VARCHAR(n) 的计数方式一致。
 * <p>
 * Java 的 String.length() 统计 UTF-16 单元：一个 emoji 算 2，而 MySQL utf8mb4 只算 1 个字符。
 * 所以 message 的 4096 上限用码点数判断，两种数据库接受的数据完全相同。
 */
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = MaxCodePoints.Validator.class)
public @interface MaxCodePoints {

    int value();

    String message() default "长度不能超过{value}个字符";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    class Validator implements ConstraintValidator<MaxCodePoints, String> {
        private int max;

        @Override
        public void initialize(MaxCodePoints annotation) {
            this.max = annotation.value();
        }

        @Override
        public boolean isValid(String value, ConstraintValidatorContext context) {
            // null 交给 @NotBlank 等注解判断
            return value == null || value.codePointCount(0, value.length()) <= max;
        }
    }
}
