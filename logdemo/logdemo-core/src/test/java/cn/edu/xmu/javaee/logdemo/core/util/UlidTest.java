package cn.edu.xmu.javaee.logdemo.core.util;

import org.junit.jupiter.api.Test;

import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** ULID 编码测试：已知向量、按时间排序、批量不重复。 */
class UlidTest {

    @Test
    void knownVectors() {
        assertEquals("00000000000000000000000000", Ulid.encode(0, 0, 0));
        assertEquals("7ZZZZZZZZZZZZZZZZZZZZZZZZZ", Ulid.encode(0xFFFF_FFFF_FFFFL, 0xFFFF, -1L));
        // ULID 规范示例 01ARYZ6S41TSV4RRFFQ69G5FAV 的时间部分对应 1469918176385 毫秒
        assertEquals("01ARYZ6S41", Ulid.of(1469918176385L).substring(0, 10));
    }

    @Test
    void sortableByTime() {
        String a = Ulid.of(1_700_000_000_000L);
        String b = Ulid.of(1_700_000_000_001L);
        assertEquals(Ulid.LENGTH, a.length());
        assertTrue(a.compareTo(b) < 0, "later timestamp sorts after earlier one");
        assertTrue(a.matches("[0-9A-HJKMNP-TV-Z]{26}"), "Crockford Base32 only");
    }

    @Test
    void noCollisionsInBatch() {
        Set<String> ids = new HashSet<>();
        for (int i = 0; i < 100_000; i++) {
            ids.add(Ulid.next());
        }
        assertEquals(100_000, ids.size());
    }

    @Test
    void rejectsOutOfRangeTimestamp() {
        assertThrows(IllegalArgumentException.class, () -> Ulid.of(-1));
        assertThrows(IllegalArgumentException.class, () -> Ulid.of(1L << 48));
    }
}
