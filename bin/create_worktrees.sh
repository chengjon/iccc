#!/bin/bash
# create_worktrees.sh - 创建多个Worktree用于多CLI协作
# 由iCCC Worktree Manager生成

set -e  # 遇到错误立即退出

# 配置
PROJECT_ROOT="${ICCC_PROJECT_ROOT:-/opt/iflow/iccc}"
WORKTREE_BASE="${ICCC_WORKTREE_BASE:-/opt/claude}"
BRANCH_PREFIX="${ICCC_BRANCH_PREFIX:-iccc-}"

TASK_FILE="${1:-tasks.txt}"

if [ ! -f "$TASK_FILE" ]; then
    echo "错误: 任务文件不存在: $TASK_FILE"
    echo "用法: ./create_worktrees.sh <任务文件>"
    exit 1
fi

echo "=== iCCC Worktree 创建工具 ==="
echo "项目根目录: $PROJECT_ROOT"
echo "任务文件: $TASK_FILE"
echo ""

cd "$PROJECT_ROOT"

# 确保主分支是最新的
echo "步骤1: 更新主分支"
git checkout main
git pull origin main
echo ""

# 读取任务列表并创建Worktree
echo "步骤2: 创建Worktree"
LINE_NUM=0
while IFS= read -r line || [ -n "$line" ]; do
    LINE_NUM=$((LINE_NUM + 1))

    # 跳过注释和空行
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "${line// }" ]] && continue

    # 解析任务信息 (格式: TASK_NAME,BRANCH_NAME,DESCRIPTION)
    TASK_NAME=$(echo "$line" | cut -d',' -f1)
    BRANCH_NAME=$(echo "$line" | cut -d',' -f2)
    DESCRIPTION=$(echo "$line" | cut -d',' -f3-)

    WORKTREE_PATH="${WORKTREE_BASE}/iccc_${TASK_NAME}"

    echo "创建Worktree #$LINE_NUM: $TASK_NAME"
    echo "  路径: $WORKTREE_PATH"
    echo "  分支: ${BRANCH_PREFIX}${BRANCH_NAME}"
    echo "  描述: $DESCRIPTION"

    # 创建Worktree和新分支
    git worktree add -b "${BRANCH_PREFIX}${BRANCH_NAME}" "$WORKTREE_PATH"

    # 创建README
    cat > "$WORKTREE_PATH/README.md" <<EOF
# iCCC项目 - $DESCRIPTION

## 任务目标
$DESCRIPTION

## 任务分配信息
- 分配给: Worker CLI-$LINE_NUM
- 分配时间: $(date '+%Y-%m-%d %H:%M')
- 主CLI: iCCC (Manager)
- 项目: iCCC
- 分支: ${BRANCH_PREFIX}${BRANCH_NAME}

## 验收标准
- [ ] 标准1: [具体描述]
- [ ] 标准2: [具体描述]
- [ ] 标准3: [具体描述]

## 工作范围
### 本Worktree范围内
- ✅ 代码开发
- ✅ 测试编写
- ✅ 文档编写

### 超出本Worktree范围（需要请示主CLI）
- ⚠️ 修改其他模块的代码
- ⚠️ 修改项目配置

## 优先级
🔴 高

## 预计工作量
- 总计: X小时

## 预计完成时间
T+Xh

## 问题请示流程
如果遇到以下情况，请向主CLI请示：
1. 需要修改其他Worktree的文件
2. 需要调整任务优先级
3. 需要额外的资源或协助

## 进度更新
### T+0h（任务开始）
- 状态: 任务理解中
- 进度: 0%

EOF

    echo "  ✅ README创建完成"
    echo ""

done < "$TASK_FILE"

# 验证所有Worktree
echo "步骤3: 验证Worktree创建"
git worktree list

echo ""
echo "=== Worktree创建完成 ==="
echo "总计创建: $LINE_NUM 个Worktree"
echo "下一步: 为每个Worker CLI提供对应的Worktree路径和分支信息"
