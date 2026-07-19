#!/usr/bin/env bash
# reference-transaction: canonical 分支历史保护
#
# 只在可拒绝的 prepared phase 裁决，且只处理 canonical 分支的记录；
# committed / aborted phase 直接放行。已有 canonical 分支的每次更新必须能
# 证明 old OID 是 new OID 的祖先（快进）：删除、零 OID、malformed 行、
# 不可解析对象、无法证明快进的更新一律拒绝；任一 canonical 记录失败即
# 拒绝整个 transaction。其它 ref（task/* 等）不受门控。
#
# canonical 分支解析顺序：
#   git config worktree-task.canonicalRef
#   → refs/heads/main（存在时）
#   → refs/heads/master（存在时）
#   → 都不存在则不门控（exotic 布局不误伤）
#
# 本 hook 不识别 worktree 角色；canonical 主工作树与 symbolic-ref 检查
# 由 worktree_task.py 入口承担。配合 assets/scripts/worktree_task.py 使用。

phase="$1"
[ "$phase" = "prepared" ] || exit 0

canonical=$(git config worktree-task.canonicalRef 2>/dev/null)
if [ -z "$canonical" ]; then
    if git show-ref --verify --quiet refs/heads/main; then
        canonical="refs/heads/main"
    elif git show-ref --verify --quiet refs/heads/master; then
        canonical="refs/heads/master"
    else
        exit 0
    fi
fi

ZERO40="0000000000000000000000000000000000000000"
ZERO64="0000000000000000000000000000000000000000000000000000000000000000"
status=0

while IFS=' ' read -r old new ref extra; do
    if [ -z "$old" ] && [ -z "$new" ] && [ -z "$ref" ]; then
        continue
    fi
    if [ -z "$old" ] || [ -z "$new" ] || [ -z "$ref" ] || [ -n "$extra" ]; then
        echo "reference-transaction: malformed record, reject transaction" >&2
        status=1
        continue
    fi
    [ "$ref" = "$canonical" ] || continue

    if [ "$old" = "$ZERO40" ] || [ "$old" = "$ZERO64" ] || \
       [ "$new" = "$ZERO40" ] || [ "$new" = "$ZERO64" ]; then
        echo "reference-transaction: $canonical zero OID not allowed" >&2
        status=1
        continue
    fi
    if ! printf '%s' "$old" | grep -qE '^[0-9a-f]{40}([0-9a-f]{24})?$' || \
       ! printf '%s' "$new" | grep -qE '^[0-9a-f]{40}([0-9a-f]{24})?$'; then
        echo "reference-transaction: $canonical malformed OID" >&2
        status=1
        continue
    fi
    if [ "$(git cat-file -t "$old" 2>/dev/null)" != "commit" ] || \
       [ "$(git cat-file -t "$new" 2>/dev/null)" != "commit" ]; then
        echo "reference-transaction: $canonical unresolvable commit" >&2
        status=1
        continue
    fi
    if ! git merge-base --is-ancestor "$old" "$new" 2>/dev/null; then
        echo "reference-transaction: $canonical non-fast-forward rejected" >&2
        status=1
        continue
    fi
done

exit $status
