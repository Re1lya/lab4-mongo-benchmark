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
 * IPv4 或 IPv6 文本格式校验（只看格式，不做 DNS 解析）。
 * IPv6 最长文本形如 ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255，共 45 个字符，
 * 这就是 clientIp 列为 VARCHAR(45) 的原因。
 */
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = IpAddress.Validator.class)
public @interface IpAddress {

    String message() default "不是合法的IPv4或IPv6地址";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};

    class Validator implements ConstraintValidator<IpAddress, String> {

        @Override
        public boolean isValid(String value, ConstraintValidatorContext context) {
            return value == null || isIpAddress(value);
        }

        public static boolean isIpAddress(String s) {
            if (s.isEmpty() || s.length() > 45) {
                return false;
            }
            return s.indexOf(':') >= 0 ? isIpv6(s) : isIpv4(s);
        }

        /** 四段 0~255 的十进制数，不允许前导 0。 */
        static boolean isIpv4(String s) {
            String[] parts = s.split("\\.", -1);
            if (parts.length != 4) {
                return false;
            }
            for (String p : parts) {
                if (p.isEmpty() || p.length() > 3 || (p.length() > 1 && p.charAt(0) == '0')) {
                    return false;
                }
                for (int i = 0; i < p.length(); i++) {
                    char c = p.charAt(i);
                    if (c < '0' || c > '9') {
                        return false;
                    }
                }
                if (Integer.parseInt(p) > 255) {
                    return false;
                }
            }
            return true;
        }

        /** 8 个 16 位分组；最多一个 :: 表示省略的连续 0 分组；末尾可嵌入 IPv4。 */
        static boolean isIpv6(String s) {
            String body = s;
            if (body.indexOf('.') >= 0) {
                int lastColon = body.lastIndexOf(':');
                if (!isIpv4(body.substring(lastColon + 1))) {
                    return false;
                }
                // 嵌入的 IPv4 占两个分组
                body = body.substring(0, lastColon + 1) + "0:0";
            }
            int doubleColon = body.indexOf("::");
            if (doubleColon < 0) {
                return groupCount(body) == 8;
            }
            if (doubleColon != body.lastIndexOf("::")) {
                return false;
            }
            int left = groupCount(body.substring(0, doubleColon));
            int right = groupCount(body.substring(doubleColon + 2));
            return left >= 0 && right >= 0 && left + right <= 7;
        }

        /** 冒号分隔的分组个数：空串为 0，任何分组不合法返回 -1。 */
        private static int groupCount(String s) {
            if (s.isEmpty()) {
                return 0;
            }
            String[] groups = s.split(":", -1);
            for (String g : groups) {
                if (g.isEmpty() || g.length() > 4) {
                    return -1;
                }
                for (int i = 0; i < g.length(); i++) {
                    char c = g.charAt(i);
                    boolean hex = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
                    if (!hex) {
                        return -1;
                    }
                }
            }
            return groups.length;
        }
    }
}
