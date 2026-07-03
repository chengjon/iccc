#!/bin/bash
# merge_and_cleanup.sh - 合并所有Worktree分支并清理
# 由iCCC Worktree Manager生成

set -e

PROJECT_ROOT="${ICCC_PROJECT_ROOT:-/opt/iflow/iccc}"
WORKTREE_BASE="${ICCC_WORKTREE_BASE:-/opt/claude}"
BRANCH_PREFIX="${ICCC_BRANCH_PREFIX:-iccc-}"

cd "$PROJECT_ROOT"

echo "=== iCCC Worktree 合并与清理工具 ==="
echo "开始时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 步骤1: 切换到main分支并更新
echo "步骤1: 切换到main分支并更新"
git checkout main
git pull origin main
echo ""

# 步骤2: 收集所有Worktree分支
echo "步骤2: 收集Worktree分支"
WORKTREE_BRANCHES=()
for worktree in "$WORKTREE_BASE"/iccc_*; do
    if [ -d "$worktree" ] && [ -d "$worktree/.git" ]; then
        cd "$worktree"
        CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        WORKTREE_BRANCHES+=("$CURRENT_BRANCH")
        echo "  - $(basename "$worktree"): $CURRENT_BRANCH"
    fi
done
echo ""

# 步骤3: 验证每个Worktree已完成
echo "步骤3: 验证Worktree完成状态"
for branch in "${WORKTREE_BRANCHES[@]}"; do
    echo "  检查分支: $branch"
done
echo ""

# 步骤4: 合并所有分支
echo "步骤4: 合并所有分支到main"
for branch in "${WORKTREE_BRANCHES[@]}"; do
    echo "  合并: $branch"

    MERGE_MESSAGE="Merge $branch: 完成协作任务

- 合并来自Worker CLI的工作成果
- 经过测试验证
- 符合项目标准

🤖 Generated with iCCC Worktree Manager
Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"

    git merge "$branch" --no-ff -m "$MERGE_MESSAGE" || {
        echo "  ⚠️  合并冲突，需要手动解决: $branch"
        echo "  解决冲突后，请运行: git merge --continue"
        exit 1
    }
done
echo ""

# 步骤5: 推送到远程
echo "步骤5: 推送到远程"
git push origin main
echo ""

# 步骤6: 清理Worktree
echo "步骤6: 清理Worktree"
for worktree in "$WORKTREE_BASE"/iccc_*; do
    if [ -d "$worktree" ]; then
        WORKTREE_NAME=$(basename "$worktree")
        echo "  删除: $WORKTREE_NAME"
        git worktree remove "$worktree" --force 2>/dev/null || true
    fi
done
echo ""

# 步骤7: 验证清理结果
echo "步骤7: 验证清理结果"
git worktree list
echo ""

echo "=== 合并与清理完成 ==="
echo "完成时间: $(date '+%Y-%m-%d %H:%M:%S')"
