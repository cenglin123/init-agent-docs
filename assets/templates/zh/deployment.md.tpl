# 部署与环境配置

> 记录部署方式、环境差异和启动约定。
> 修改本文件后同步更新 [CHANGELOG.md](../CHANGELOG.md)。

## 环境变量

<!-- 列出必需的环境变量及其用途，不列默认值（默认值看代码） -->

<!-- 示例填充：

| 变量 | 用途 | 必填 | 备注 |
|------|------|------|------|
| `DATABASE_URL` | 主数据库连接 | ✅ | 生产用 postgres://，本地可用 sqlite:/// |
| `REDIS_URL` | 会话存储 | ✅ | 没有 fallback，缺失会启动失败 |
| `OPENAI_API_KEY` | 调用模型 | ✅ | 不要硬编码，仅从 .env 读取 |
| `LOG_LEVEL` | 日志等级 | ❌ | 默认 INFO，调试时设为 DEBUG |
-->

## 启动方式

<!-- 开发环境和生产环境的启动命令 -->

<!-- 示例填充：

### 开发环境
```bash
uv sync
cp .env.example .env  # 然后填入本地值
uv run uvicorn app.main:app --reload --port 8000
```

### 生产环境
- 由 systemd 单元 `app.service` 拉起 `gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app`
- 静态资源由 Caddy 反代，监听 443
- 日志写入 `/var/log/app/`（持久化挂载）
-->

## 持久化与备份

<!-- 哪些目录是持久化挂载？数据库怎么备份？应该 24 小时还是 7 天？-->

## 部署陷阱

<!-- 与 docs/pitfalls.md 区分：这里只放部署相关的、其他地方不会遇到的坑 -->
