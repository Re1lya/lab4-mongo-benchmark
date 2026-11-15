package cn.edu.xmu.javaee.logdemo.core.validation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 不依赖数据库的单元测试：IP 校验、按字符计数。 */
class ValidationTest {

    @Test
    void ipAddressValidation() {
        for (String ok : new String[]{"10.0.0.1", "255.255.255.255", "0.0.0.0", "::1", "::", "2001:db8::1",
                "fe80:0:0:0:0:0:0:1", "1:2:3:4:5:6:7::", "::ffff:192.168.1.1",
                "ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255"}) {
            assertTrue(IpAddress.Validator.isIpAddress(ok), ok);
        }
        for (String bad : new String[]{"", "1.2.3", "1.2.3.4.5", "256.1.1.1", "01.2.3.4", "a.b.c.d", "1::2::3",
                ":::", "12345::1", "1:2:3:4:5:6:7:8:9", "gggg::1", "localhost", "1.2.3.4::"}) {
            assertFalse(IpAddress.Validator.isIpAddress(bad), bad);
        }
    }

    @Test
    void maxCodePointsCountsCharactersNotUtf16Units() {
        MaxCodePoints.Validator v = new MaxCodePoints.Validator();
        v.initialize(new MaxCodePoints() {
            public int value() { return 3; }
            public String message() { return ""; }
            public Class<?>[] groups() { return new Class<?>[0]; }
            @SuppressWarnings("unchecked")
            public Class<? extends jakarta.validation.Payload>[] payload() { return new Class[0]; }
            public Class<? extends java.lang.annotation.Annotation> annotationType() { return MaxCodePoints.class; }
        });
        assertTrue(v.isValid("😀😀😀", null), "3 emoji = 3 characters although String.length() is 6");
        assertFalse(v.isValid("😀😀😀😀", null));
        assertTrue(v.isValid(null, null));
    }
}
