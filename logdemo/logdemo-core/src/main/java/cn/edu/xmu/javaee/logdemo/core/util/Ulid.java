package cn.edu.xmu.javaee.logdemo.core.util;

import java.util.concurrent.ThreadLocalRandom;

/**
 * ULID（Universally Unique Lexicographically Sortable Identifier）生成器。
 * <p>
 * 26 个 Crockford Base32 字符 = 48 位毫秒时间戳（前 10 个字符）+ 80 位随机数（后 16 个字符）。
 * 前缀是时间，所以按字符串排序就是按生成时间排序：MySQL 的聚簇主键插入总在索引末尾，
 * 不会像随机 UUID 那样频繁分裂页；MongoDB 的 _id 索引同理。
 * 随机部分用 ThreadLocalRandom，避免高并发下争用同一个随机数生成器。
 */
public final class Ulid {

    private static final char[] ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ".toCharArray();

    public static final int LENGTH = 26;

    private Ulid() {
    }

    /** 用当前时间生成一个 ULID。 */
    public static String next() {
        return of(System.currentTimeMillis());
    }

    /** 用指定毫秒时间戳生成一个 ULID（随机部分每次不同）。 */
    public static String of(long epochMillis) {
        ThreadLocalRandom random = ThreadLocalRandom.current();
        return encode(epochMillis, random.nextLong() & 0xFFFFL, random.nextLong());
    }

    /**
     * 编码：timestamp 取低 48 位；随机数 80 位 = randomHigh16（高 16 位）+ randomLow64（低 64 位）。
     */
    static String encode(long epochMillis, long randomHigh16, long randomLow64) {
        if (epochMillis < 0 || epochMillis > 0xFFFF_FFFF_FFFFL) {
            throw new IllegalArgumentException("timestamp out of ULID range: " + epochMillis);
        }
        char[] chars = new char[LENGTH];
        long time = epochMillis;
        for (int i = 9; i >= 0; i--) {
            chars[i] = ALPHABET[(int) (time & 31)];
            time >>>= 5;
        }
        long high = randomHigh16 & 0xFFFFL;
        long low = randomLow64;
        for (int i = LENGTH - 1; i >= 10; i--) {
            chars[i] = ALPHABET[(int) (low & 31)];
            low = (low >>> 5) | ((high & 31) << 59);
            high >>>= 5;
        }
        return new String(chars);
    }
}
