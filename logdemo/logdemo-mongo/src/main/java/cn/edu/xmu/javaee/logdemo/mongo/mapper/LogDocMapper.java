package cn.edu.xmu.javaee.logdemo.mongo.mapper;

import cn.edu.xmu.javaee.logdemo.mongo.po.LogDoc;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

import java.time.Instant;
import java.util.List;

/**
 * Spring Data MongoDB Repository，条件与 JPA 版完全相同。生成的查询形如：
 * <pre>
 * db.log_record.find({level: "INFO", createdAt: {$gte: from, $lt: to}})
 *              .sort({createdAt: -1, _id: -1}).skip(n).limit(size)
 * </pre>
 * 对应索引 {level: 1, createdAt: -1, _id: -1}。返回 List，不执行 count。
 * 注意：派生方法名 findByCreatedAtGreaterThanEqualAndCreatedAtLessThan 在 Spring Data MongoDB 中
 * 会因同一字段出现两次而报错，所以这里显式写出查询文档。
 */
public interface LogDocMapper extends MongoRepository<LogDoc, String> {

    @Query("{ 'level': ?0, 'createdAt': { '$gte': ?1, '$lt': ?2 } }")
    List<LogDoc> findPage(String level, Instant from, Instant to, Pageable pageable);

    @Query("{ 'createdAt': { '$gte': ?0, '$lt': ?1 } }")
    List<LogDoc> findPageAllLevels(Instant from, Instant to, Pageable pageable);
}
