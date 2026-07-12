# 公司内网开发机配置教程

本文档面向在公司内网开发机上启动本项目的开发者。目标是做到：

- Python 依赖正常安装
- 前端 npm 依赖走公司内网镜像
- 复用已有 PostgreSQL
- 一键启动前后端
- 遇到问题时能快速定位

---

## 1. 适用范围

本教程适用于以下场景：

1. 机器可以访问 Python 官方包源，或者至少能正常 `pip install`
2. npm 需要使用公司内网镜像
3. PostgreSQL 已经安装并可连接
4. 不使用 Docker
5. 不通过 request / HTTP 方式加载数据

如果你的环境是完全离线或需要自动安装 PostgreSQL，本教程不适用。

---

## 2. 推荐启动方式

公司内网开发机建议直接使用：

```bat
start.intranet.bat
```

它会自动：

- 检查 `.venv`
- 缺失时执行 bootstrap
- 校验数据库连接
- 执行迁移
- 加载种子数据
- 启动后端
- 启动前端

如果你想分开执行，也可以手动跑：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\bootstrap_dev.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\launch_dev.ps1 -Mode intranet
```

---

## 3. 需要提前确认的配置

### 3.1 Python

请确认以下条件：

- 已安装 Python 3.11 或更高版本
- `python` 命令可直接使用
- 能正常执行 `python -m venv`
- 能正常执行 `pip install -r requirements.txt`

建议检查：

```bat
python --version
pip --version
```

如果 `python` 无法识别，通常需要把 Python 安装目录加入 PATH。

---

### 3.2 Node / npm

本项目要求前端依赖使用公司内网 npm 镜像。

你需要确认：

- `node` 和 `npm` 可用
- `frontend\.npmrc` 存在
- `frontend\.npmrc` 中的 registry 指向公司内网镜像

检查命令：

```bat
node --version
npm --version
npm config get registry
```

项目当前约定使用仓库内的 `frontend/.npmrc`，不要依赖个人全局 npm 配置。

如果你需要修改镜像地址，只改 `frontend/.npmrc` 即可。

例如：

```ini
registry=https://npm.company.local/repository/npm-group/
```

如果公司实际镜像地址不同，请替换成你们真实可用的地址。

---

### 3.3 PostgreSQL

数据库已由你本机或公司环境提供，不需要 Docker，也不需要脚本安装。

需要确认：

- PostgreSQL 服务已启动
- 可以远程或本地连接
- 数据库、用户名、密码与 `.env` 一致

默认配置在 `.env.example` 中：

```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=solver
DB_PASSWORD=solver123
DB_NAME=solver_db
```

如果你的数据库参数不同，请修改仓库根目录下的 `.env`。

---

## 4. 需要修改的配置文件

### 4.1 `.env`

这是后端运行最关键的配置文件。

通常需要检查或修改：

- `DB_HOST`
- `DB_PORT`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DATABASE_URL`（可选，覆盖自动拼接）
- `APP_ENV`
- `DEBUG`
- `LOG_LEVEL`
- `SOLVER_MAX_TIME_SECONDS`

示例：

```env
DB_HOST=localhost
DB_PORT=5432
DB_USER=solver
DB_PASSWORD=solver123
DB_NAME=solver_db
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO
SOLVER_MAX_TIME_SECONDS=30.0
```

如果数据库账���不是默认值，最常见的问题就是 `.env` 没改对。

---

### 4.2 `frontend/.npmrc`

这是前端依赖安装的核心配置。

必须确认这里有公司内网镜像地址，例如：

```ini
registry=https://npm.company.local/repository/npm-group/
```

如果 registry 不对，`npm install` 可能会：

- 访问公网失败
- 安装超时
- 下载依赖过慢
- 走到了错误的源

如果你更换了公司镜像地址，这个文件要同步修改。

---

### 4.3 `deploy/scripts/launch_dev.ps1`

这个脚本提供模式分流：

- `docker`
- `local`
- `intranet`

如果你新增启动行为，通常需要修改这里。

当前内网开发机默认使用：

```powershell
-Mode intranet
```

---

### 4.4 `deploy/scripts/bootstrap_dev.ps1`

这个脚本负责首次环境准备。

如果你要调整以下内容，需要修改它：

- Python 依赖安装方式
- npm registry 校验逻辑
- `.env` 初始化行为
- 首次环境检查顺序

---

## 5. 首次部署步骤

建议按下面顺序执行一次：

### 步骤 1：创建 `.env`

如果仓库根目录下没有 `.env`，先复制一份：

```bat
copy .env.example .env
```

然后根据你本机 PostgreSQL 修改数据库连接信息。

---

### 步骤 2：确认 npm registry

打开 `frontend/.npmrc`，确保 registry 指向公司内网镜像。

然后检查：

```bat
cd frontend
npm config get registry
```

如果不对，请先改 `.npmrc`，不要只改全局配置。

---

### 步骤 3：执行 bootstrap

首次运行建议执行：

```bat
start.intranet.bat
```

或者手工执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\bootstrap_dev.ps1
```

bootstrap 会做这些事：

1. 创建 `.venv`
2. 安装 Python 依赖
3. 检查 npm registry
4. 安装前端依赖
5. 检查数据库连通性

---

### 步骤 4：执行启动

如果 bootstrap 成功，可以直接启动：

```bat
start.intranet.bat
```

或者单独执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\scripts\launch_dev.ps1 -Mode intranet
```

launch 会做这些事：

1. 检查数据库连接
2. 执行 Alembic migration
3. 加载基础 seed
4. 启动后端
5. 启动前端

---

## 6. 常见问题

### 问题 1：`python` 或 `npm` 命令找不到

现象：

- 终端提示 `'python' 不是内部或外部命令`
- 或 `'npm' 不是内部或外部命令`

解决办法：

- 重新安装 Python / Node.js
- 确认安装目录已加入 PATH
- 重新打开终端

---

### 问题 2：npm 安装失败或很慢

常见原因：

- `frontend/.npmrc` 没配对
- registry 地址不是公司内网镜像
- 镜像不可达

排查方法：

```bat
cd frontend
npm config get registry
```

如果不是公司镜像，请修改 `frontend/.npmrc`。

---

### 问题 3：数据库连接失败

常见原因：

- PostgreSQL 没启动
- `.env` 中的数据库账号密码不对
- 端口不是 5432
- 防火墙或权限问题

排查方法：

```bat
python scripts/test_db_connection.py
```

如果失败，优先检查 `.env`。

---

### 问题 4：迁移失败

常见原因：

- 数据库版本和迁移脚本不一致
- 表已经存在但迁移没跑过
- `alembic` 指向了错误的数据库

解决建议：

- 先确认 `python scripts/test_db_connection.py` 成功
- 再单独跑：

```bat
alembic upgrade head
```

---

### 问题 5：seed 加载失败

常见原因：

- 数据已经存在，导致重复插入
- 种子 SQL 与当前 schema 不兼容
- SQL 文件路径错误

说明：

- 当前 `scripts/load_seed_data.py` 是按分号拆分 SQL 执行
- 复杂的 PL/pgSQL block 不适合直接放进种子文件

解决建议：

- 清理已有数据后重试
- 检查 SQL 是否为纯语句
- 确保路径正确

---

### 问题 6：前端启动了，但页面访问不到

常见原因：

- Vite 还没完全启动
- 端口 5173 被占用
- 前端窗口里已经报错

排查方法：

- 看前端启动窗口是否成功输出地址
- 检查 `http://localhost:5173`
- 如端口冲突，换端口或关闭占用进程

---

### 问题 7：后端启动了但页面请求失败

常见原因：

- 后端连接数据库失败
- `.env` 错误
- 迁移未完成
- 前端 API baseURL 配置有误

排查步骤：

1. 打开 `http://localhost:8000/docs`
2. 先确认后端接口可访问
3. 再检查前端控制台错误

---

## 7. 调试建议

当你不确定问题在哪里时，按下面顺序排查最省时间：

1. 检查 `python --version`
2. 检查 `npm --version`
3. 检查 `frontend/.npmrc`
4. 检查 `.env`
5. 运行 `python scripts/test_db_connection.py`
6. 单独执行 `alembic upgrade head`
7. 单独执行 `npm install`
8. 再执行 `start.intranet.bat`

---

## 8. 推荐的最小修改清单

如果你换机器，通常只需要改这些：

- `.env`
- `frontend/.npmrc`

如果你改了启动逻辑，再看：

- `deploy/scripts/bootstrap_dev.ps1`
- `deploy/scripts/launch_dev.ps1`

---

## 9. 相关入口

- `start.intranet.bat`：公司内网开发机一键入口
- `deploy/scripts/bootstrap_dev.ps1`：首次环境准备
- `deploy/scripts/launch_dev.ps1`：日常启动
- `README.md`：快速入口说明
- `.env.example`：默认配置模板
