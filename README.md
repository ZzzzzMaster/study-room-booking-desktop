# 自习室预约系统 · 桌面版

校园自习室座位预约系统。学生在网页端选座、预约、续约、离座；后端定时扫描每笔预约，**到期前 15 分钟推送提醒、超时 30 分钟自动释放座位**。管理员可维护自习室与座位、查看全场预约。

整套系统**零第三方依赖**：HTTP 服务、WebSocket、认证签名、定时任务全部用 Python 标准库手写实现，`pip install` 都不需要。

## 功能

**学生端**

- 注册 / 登录（学号 + 密码，PBKDF2-SHA256 加盐哈希存储）
- 自习室列表与座位图实时状态（可用 / 已预约 / 使用中 / 禁用 / 损坏，是否带插座）
- 按日期 + 时段选座预约，单次最长 4 小时，自动检测同一座位的时间冲突
- 我的预约：续约、离座、取消
- WebSocket 实时推送「即将到期提醒」「已到期请离座」「座位已释放」

**管理端**

- 自习室增删改（名称、位置、开放时段、开关状态）
- 座位增删改与状态维护（可用 / 禁用 / 损坏），是否带插座
- 全场预约记录查询

## 技术栈

| 层 | 实现 |
| --- | --- |
| HTTP 服务 | `http.server.ThreadingHTTPServer`，REST 路由表 + SPA 静态资源回退 |
| 实时推送 | `socket` 手写 RFC 6455 WebSocket（握手、帧编解码、心跳、按用户定向推送 / 全员广播） |
| 存储 | SQLite，WAL 模式 + `busy_timeout`，写操作显式 `BEGIN IMMEDIATE` 保证并发安全 |
| 认证 | PBKDF2-HMAC-SHA256（10 万次迭代）+ HMAC-SHA256 签名 token（类 JWT，24 小时有效） |
| 定时任务 | `threading` 后台线程，每 30 秒幂等扫描，状态迁移全部带条件 UPDATE |
| 前端 | 原生 HTML / CSS / JavaScript，无框架，hash 路由单页应用 |

## 目录结构

```
.
├── app
│   ├── backend          # 服务端（Python 3 标准库）
│   │   ├── server.py    # 入口：HTTP 服务 + 静态资源 + WebSocket 升级
│   │   ├── http_api.py  # REST 接口与路由表
│   │   ├── ws_server.py # 手写 WebSocket 服务
│   │   ├── scheduler.py # 提醒 / 到期 / 超时释放 定时扫描
│   │   ├── db.py        # 建表、种子数据、连接管理
│   │   ├── auth.py      # 密码哈希与 token 签名
│   │   └── config.py    # 时段、限制、可环境变量覆盖的配置
│   ├── frontend         # 前端单页应用
│   │   ├── index.html
│   │   ├── css/style.css
│   │   └── js/{api,ws,ui,app}.js + js/views/{auth,rooms,mybookings,admin}.js
│   └── data             # 运行时数据（数据库、签名密钥，已加入 .gitignore）
├── run.bat              # Windows 源码启动脚本
├── run.sh               # macOS / Linux 源码启动脚本
└── 使用说明.txt          # 打包版（exe）使用说明
```

> 仓库只包含源码。打包版目录里的 `runtime/`（约 165 MB 内置 Python 运行时）与编译好的 `自习室预约系统.exe` 属于构建产物，未纳入版本管理。

## 快速开始

### 方式一：源码运行

需要 Python 3.10 及以上，无其他依赖。

```bash
cd app/backend
python server.py
```

或直接双击 `run.bat`（Windows）/ 执行 `./run.sh`（macOS、Linux）。启动后打开 <http://127.0.0.1:8000>。

首次启动会自动建库并写入种子数据：一个默认管理员账号和两个演示自习室（含无插座、损坏、禁用座位等边界情况）。

默认管理员账号的学号与密码定义在 `app/backend/db.py` 的 `DEFAULT_ADMIN_STUDENT_ID` / `DEFAULT_ADMIN_PASSWORD` 中，**部署或公开使用前请修改为自己的账号密码**。

局域网内其他设备（手机、同学电脑）访问：服务默认监听 `0.0.0.0`，用 `http://<本机局域网 IP>:8000` 即可，需放行防火墙。

### 方式二：打包版运行

打包版是免安装的 Windows 程序：双击 `自习室预约系统.exe` 即自动启动服务并弹出独立窗口，无需安装 Python。打包版依赖同目录下的 `runtime/` 与 `app/`，两者均为本地构建产物，未随源码入库。详见 [使用说明.txt](使用说明.txt)。

## 配置

均在 `app/backend/config.py` 中，可用环境变量覆盖：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SRR_HOST` | `0.0.0.0` | 监听地址，仅本机使用可设 `127.0.0.1` |
| `SRR_PORT` | `8000` | 服务端口 |
| `SRR_DB_FILE` | `app/data/study_room.db` | 数据库路径 |
| `SRR_SCAN_INTERVAL` | `30` | 定时扫描间隔（秒） |
| `SRR_REMIND_MINUTES` | `15` | 到期前多少分钟提醒 |
| `SRR_GRACE_MINUTES` | `30` | 到期后多少分钟自动释放座位 |

业务常量：开放时段 `08:00–22:00`（1 小时粒度时间槽）、单次预约最长 `4` 小时、token 有效期 `24` 小时。

## 接口一览

除注册、登录外均需请求头 `Authorization: Bearer <token>`。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/register` | 公开 | 注册学生账号 |
| POST | `/api/login` | 公开 | 登录，返回 token |
| POST | `/api/logout` | 登录 | 退出 |
| GET | `/api/me` | 登录 | 当前用户信息 |
| GET | `/api/rooms` | 登录 | 自习室列表 |
| GET | `/api/rooms/{id}/seats?date=&start=&end=` | 登录 | 座位状态（含指定时段占用情况） |
| GET | `/api/my-bookings` | 登录 | 我的预约 |
| POST | `/api/bookings` | 登录 | 创建预约 |
| POST | `/api/bookings/{id}/renew` | 本人 | 续约 |
| POST | `/api/bookings/{id}/leave` | 本人 | 离座 |
| POST | `/api/bookings/{id}/cancel` | 本人 | 取消预约 |
| GET | `/api/admin/bookings` | 管理员 | 全场预约查询 |
| POST/PUT/DELETE | `/api/admin/rooms[/{id}]` | 管理员 | 自习室维护 |
| POST/PUT/DELETE | `/api/admin/seats[/{id}]` | 管理员 | 座位维护 |
| PUT | `/api/admin/seats/{id}/status` | 管理员 | 修改座位状态 |
| WS | `/ws?token=<token>` | 登录 | 实时消息推送 |

## 预约状态机

```
创建            booking: reserved   seat: reserved
达到结束时间     booking: occupied   seat: occupied    → 推送「已到期，请续约或离座」
超时 30 分钟     booking: expired    seat: available   → 广播「座位已释放」
续约            end_time 延后，重置提醒标记
离座 / 取消      booking: completed / cancelled，seat: available
```

所有状态迁移以后端时间为准，每步 `UPDATE` 都附带状态与标记位条件，重复执行安全（幂等），不依赖前端计时。

## 数据表

`users`（用户与角色）、`rooms`（自习室）、`seats`（座位，含插座与状态）、`bookings`（预约，含提醒 / 到期标记）。索引覆盖「座位 + 日期 + 状态」冲突检测、用户预约查询与按自习室查座位。

## 说明

- 数据库与 `secret.key` 属运行时数据，删除 `app/data/` 下的 `.db` 文件即可重置并重建演示数据。
- 前端未做构建，改完 JS / CSS 刷新浏览器即可生效（静态资源已设 `no-store`）。
