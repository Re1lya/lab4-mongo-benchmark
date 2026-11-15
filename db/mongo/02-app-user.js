// 实验四 MongoDB 应用账号：lab4app 只能查询和插入 lab4_log.log_record（与 MySQL 版权限相同）。
// 密码从环境变量 LAB4_APP_PASSWORD 读取，不写入仓库：
//   LAB4_APP_PASSWORD='<随机密码>' mongosh -u root -p --authenticationDatabase admin 02-app-user.js
// 部署脚本 deploy/scripts/init-mongo.sh 会在服务器上生成随机密码并保存为 Docker secret。

const password = process.env.LAB4_APP_PASSWORD;
if (!password) {
  throw new Error('LAB4_APP_PASSWORD is not set');
}

const target = db.getSiblingDB('lab4_log');

const roleName = 'lab4LogReadInsert';
const privileges = [
  { resource: { db: 'lab4_log', collection: 'log_record' }, actions: ['find', 'insert'] }
];
if (target.getRole(roleName)) {
  target.updateRole(roleName, { privileges, roles: [] });
} else {
  target.createRole({ role: roleName, privileges, roles: [] });
}

if (target.getUser('lab4app')) {
  target.updateUser('lab4app', { pwd: password, roles: [{ role: roleName, db: 'lab4_log' }] });
} else {
  target.createUser({ user: 'lab4app', pwd: password, roles: [{ role: roleName, db: 'lab4_log' }] });
}

printjson({ user: 'lab4app', db: 'lab4_log', role: roleName });
