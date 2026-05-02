# 已知环境陷阱

> 记录开发和部署中遇到的坑。每条记录包括：现象、原因、解决方案。
> 修改本文件后同步更新 [CHANGELOG.md](../CHANGELOG.md)。

## UTF-8 编码

项目中可能包含中文文件名、中文注释、中文文档内容，必须全链路确保 UTF-8 编码，否则会出现乱码、读写失败、diff 异常等问题。

### 文件编码
**现象**：中文注释或字符串在某些环境下显示为乱码，或读取文件时抛出 UnicodeDecodeError / GBK codec 错误。
**原因**：Windows 默认使用 GBK/CP936 编码，而非 UTF-8。新建文件可能继承系统默认编码。
**解决**：
- 所有源码文件和文档统一使用 UTF-8（无 BOM）编码
- Python 读写文件时显式指定 `encoding='utf-8'`，不依赖系统默认编码
- 在 `.editorconfig` 中设置 `charset = utf-8`（如项目使用 EditorConfig）
- VS Code 用户在 settings.json 中设置 `"files.encoding": "utf-8"`

### Git 与中文路径
**现象**：`git status` 或 `git diff` 中，中文文件名显示为 `\345\274\200\345\217\221...` 这样的八进制转义序列，无法阅读。
**原因**：Git 默认对非 ASCII 文件名进行 quote 转义。
**解决**：执行 `git config --global core.quotepath false`，让 Git 原样显示中文文件名。

### 终端与 Shell
**现象**：脚本输出中文时终端显示乱码，或 `print()` 抛出编码错误。
**原因**：终端代码页不是 UTF-8（Windows 默认 CP936）。
**解决**：
- Windows Terminal 默认已支持 UTF-8，推荐使用
- 旧版 cmd 可执行 `chcp 65001` 切换到 UTF-8 代码页
- Python 脚本开头可设置 `PYTHONUTF8=1` 环境变量强制 UTF-8 模式

<!-- 后续遇到新的陷阱时，按上面的格式继续添加。 -->
