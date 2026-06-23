# [项目名]

<!-- 生成本文件前，用第 0 步收集的信息填充所有 [方括号] 占位符。 -->
<!-- 最终文件不得残留 HTML 注释或 [方括号] 占位符。 -->

[1–2 句话说明这个项目做什么、面向谁。]

## 快速开始

### 环境要求

<!-- 列出运行本项目所需的环境：语言版本、依赖工具、操作系统要求等。示例：
- Python 3.11+
- Node.js 18+
- Docker (可选)
-->

### 安装与运行

<!-- 从项目的 package.json / pyproject.toml / Makefile / CI 等提取精确命令。示例： -->

```bash
# 克隆仓库
git clone [仓库地址]
cd [项目目录]

# 安装依赖
[依赖安装命令，如 pip install -e ".[dev]" / npm install / go mod download]

# 启动开发服务器
[启动命令，如 npm run dev / python -m uvicorn main:app --reload]
```

### 测试

```bash
[测试命令，如 pytest / npm test / go test ./...]
```

<!-- 如有 lint/format 命令也列出： -->
```bash
[lint 命令，如 ruff check / npm run lint]
```

## 项目结构

<!-- 简要说明关键目录的职责。只列最顶层和最重要的，不要逐文件列举。示例： -->

```
[项目根]/
├── src/           # 源代码
├── tests/         # 测试
├── docs/          # 文档（详见 docs/overview.md）
└── scripts/       # 工具脚本
```

<!-- 如有架构文档，指向它： -->
详细的架构说明见 [docs/overview.md](docs/overview.md)。

## 文档

| 文档 | 说明 |
|------|------|
| [docs/overview.md](docs/overview.md) | 系统架构与设计决策 |
| [docs/api.md](docs/api.md) | API 约定（如有） |
| [docs/deployment.md](docs/deployment.md) | 部署与环境配置 |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | 变更记录 |

<!-- 根据项目实际情况裁剪：没有 API 删 api.md 行，没有部署删 deployment.md 行。 -->

## 贡献

<!-- 根据项目实际约定填写。示例： -->

1. Fork 本仓库
2. 创建功能分支：`git checkout -b feat/your-feature`
3. 提交更改：`git commit -m "feat: your feature description"`
4. 推送分支：`git push origin feat/your-feature`
5. 创建 Pull Request

**提交规范**：使用 Conventional Commit 风格（`feat:` / `fix:` / `chore:` 等）。

<!-- 如项目有更详细的贡献指南，指向它： -->
<!-- 详见 [CONTRIBUTING.md](CONTRIBUTING.md)。 -->

## AI Agent 协作

本仓库配置了面向 AI Agent 的文档体系。如果你是 AI Agent，请加载 [AGENTS.md](AGENTS.md)（或 [CLAUDE.md](CLAUDE.md) / [GEMINI.md](GEMINI.md)）获取行为规则和信息导航。

## 许可证

<!-- 填入许可证类型，如 MIT / Apache-2.0 / Proprietary。无许可证时删除本节。 -->
[许可证类型]
