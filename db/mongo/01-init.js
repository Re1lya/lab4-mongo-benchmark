// 实验四 MongoDB 初始化：库 lab4_log、集合 log_record、校验规则、索引（可重复执行）。
// 执行（root 账号）：mongosh -u root -p --authenticationDatabase admin 01-init.js
//
// MongoDB 没有固定表结构，用 $jsonSchema 校验器在数据库层实现与 MySQL 列定义相同的约束：
// 必填字段、类型、长度上限、level 取值范围；additionalProperties:false 禁止出现其他字段。

const dbName = 'lab4_log';
const collName = 'log_record';
const target = db.getSiblingDB(dbName);

const validator = {
  $jsonSchema: {
    bsonType: 'object',
    required: ['_id', 'level', 'source', 'message', 'createdAt'],
    additionalProperties: false,
    properties: {
      _id: { bsonType: 'string', minLength: 26, maxLength: 26, description: '业务主键（ULID）' },
      traceId: { bsonType: 'string', maxLength: 64, description: '链路追踪标识，可省略' },
      level: { enum: ['TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR'] },
      source: { bsonType: 'string', maxLength: 128 },
      message: { bsonType: 'string', maxLength: 4096 },
      clientIp: { bsonType: 'string', maxLength: 45 },
      createdAt: { bsonType: 'date', description: '日志产生时间（BSON Date，UTC）' }
    }
  }
};

if (target.getCollectionNames().includes(collName)) {
  target.runCommand({ collMod: collName, validator, validationLevel: 'strict', validationAction: 'error' });
} else {
  target.createCollection(collName, { validator, validationLevel: 'strict', validationAction: 'error' });
}

// 与 MySQL 的 idx_level_created(level, created_at, id)、idx_created(created_at, id) 对应。
// 查询按 {createdAt:-1, _id:-1} 排序，索引方向与之一致，可以直接按索引顺序取前 N 条。
target[collName].createIndex({ level: 1, createdAt: -1, _id: -1 }, { name: 'idx_level_created' });
target[collName].createIndex({ createdAt: -1, _id: -1 }, { name: 'idx_created' });

printjson({ collection: `${dbName}.${collName}`, indexes: target[collName].getIndexes().map(i => i.name) });
