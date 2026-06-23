# API 约定

> 记录 API 的设计约定和非显而易见的行为。具体端点列表可从代码获取，这里只记约定。
> 修改本文件后同步更新 [CHANGELOG.md](CHANGELOG.md)。

<!-- ⓘ 本文档的治理规则见 AGENTS.md「文档维护原则 → docs/ 文件的治理规则」段 -->

## 通用约定

<!-- 例如：认证方式、错误响应格式、分页约定、版本策略 -->

<!-- 示例填充（按项目实际情况替换；用不到的整段删除）：

### 认证
- 请求头：`Authorization: Bearer <token>`
- token 由 `/auth/login` 颁发，过期时间 24h；过期后由前端用 refresh token 主动刷新，后端不做被动续期
- 内部服务间调用使用 mTLS，不走 Bearer

### 错误响应格式
所有非 2xx 响应统一为：
```json
{ "error": { "code": "RESOURCE_NOT_FOUND", "message": "...", "details": {} } }
```
- `code`：业务错误码（大写下划线），与 HTTP 状态码解耦——同一个 HTTP 4xx 可能对应多个 code
- `message`：给人读的描述，不要在前端用它做分支判断
- `details`：可选，结构由 code 决定

### 分页
- 查询参数：`?page=1&page_size=20`，page 从 1 开始
- 响应：`{ "items": [...], "total": 123, "page": 1, "page_size": 20 }`
- `page_size` 上限 100，超过会被截断而非报错

### 版本策略
- URL 前缀 `/api/v1/`；破坏性变更新增 `/api/v2/`，老版本至少保留 6 个月
- 仅新增字段不算破坏性变更，不需要升版本
-->
