# Known Environment Pitfalls

> Records bumps we've hit in development or deployment. Each entry: symptom, cause, fix.
> After editing, update [CHANGELOG.md](../CHANGELOG.md).

## UTF-8 Encoding

If the project contains non-ASCII file names, comments, or docs, the whole toolchain must be UTF-8 or you'll hit mojibake, decode errors, and bad diffs.

### File encoding
**Symptom**: non-ASCII comments or strings show as garbage in some environments, or file reads raise `UnicodeDecodeError` / GBK codec errors.
**Cause**: Windows defaults to GBK/CP936, not UTF-8. New files may inherit the system default.
**Fix**:
- Save all source and doc files as UTF-8 (no BOM).
- In Python, always pass `encoding='utf-8'` — don't rely on system default.
- In `.editorconfig`, set `charset = utf-8` (if the project uses EditorConfig).
- VS Code users: set `"files.encoding": "utf-8"` in settings.json.

### Git and non-ASCII paths
**Symptom**: `git status` / `git diff` show non-ASCII file names as `\345\274\200\345\217\221...` octal escapes.
**Cause**: Git quote-escapes non-ASCII file names by default.
**Fix**: `git config --global core.quotepath false`.

### Terminal & shell
**Symptom**: non-ASCII script output shows garbage, or `print()` raises encoding errors.
**Cause**: terminal code page isn't UTF-8 (Windows default is CP936).
**Fix**:
- Use Windows Terminal (UTF-8 by default).
- Legacy cmd: `chcp 65001` switches to UTF-8.
- Set `PYTHONUTF8=1` to force Python into UTF-8 mode.

<!-- Append new pitfalls below in the same format. -->
