#!/bin/bash
# monitor_worktrees.sh - 监控所有Worktree的状态
# 由iCCC Worktree Manager生成

set -e

PROJECT_ROOT="${ICCC_PROJECT_ROOT:-/opt/iflow/iccc}"
WORKTREE_BASE="${ICCC_WORKTREE_BASE:-/opt/claude}"

cd "$PROJECT_ROOT"

echo "=== iCCC Worktree 状态监控 ==="
echo "监控时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 列出所有Worktree
echo "1. Worktree列表:"
git worktree list
echo ""

# 检查每个Worktree的未提交修改
echo "2. 各Worktree文件修改统计:"
for worktree in "$WORKTREE_BASE"/iccc_*; do
    if [ -d "$worktree" ] && [ -d "$worktree/.git" ]; then
        echo ""
        echo "=== $(basename "$worktree") ==="
        cd "$worktree"

        MODIFIED=$(git status --short 2>/dev/null | wc -l)
        echo "  未提交文件数: $MODIFIED"

        LATEST_COMMIT=$(git log --oneline -1 2>/dev/null)
        echo "  最新提交: $LATEST_COMMIT"

        # 检查README进度更新
        if [ -f "README.md" ]; then
            if grep -q "状态: 进行中" README.md 2>/dev/null; then
                echo "  状态: 🔄 进行中"
            elif grep -q "状态: 阻塞" README.md 2>/dev/null; then
                echo "  状态: ⚠️ 阻塞"
            elif grep -q "状态: 完成" README.md 2>/dev/null; then
                echo "  状态: ✅ 完成"
            fi
        fi
    fi
done

echo ""
echo "=== 监控完成 ==="
