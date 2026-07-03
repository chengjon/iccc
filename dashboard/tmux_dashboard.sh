#!/bin/bash
#
# iCCC Tmux Dashboard
# 用于监控多CLI协作开发平台的实时状态
#

# 配置参数
SESSION_NAME="iccc"
PROJECT_ROOT="${1:-$(pwd)}"
ICCC_DIR="$PROJECT_ROOT/.iccc"
LOG_DIR="$ICCC_DIR/.logs"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 窗口配置
WINDOWS=(
    "agents:Agent状态监控"
    "tasks:任务跟踪"
    "events:实时事件"
    "logs:系统日志"
    "quality:质量监控"
    "system:系统状态"
)

# 初始化仪表板
init_dashboard() {
    echo -e "${BLUE}🚀 启动 iCCC Tmux Dashboard...${NC}"

    # 检查tmux是否安装
    if ! command -v tmux &> /dev/null; then
        echo -e "${RED}错误: tmux未安装${NC}"
        exit 1
    fi

    # 如果会话已存在，先杀死
    if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
        echo -e "${YELLOW}会话已存在，正在重启...${NC}"
        tmux kill-session -t "$SESSION_NAME"
    fi

    # 创建主会话
    tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_ROOT"

    # 创建所有窗口
    for window_config in "${WINDOWS[@]}"; do
        window_name="${window_config%%:*}"
        window_title="${window_config##*:}"

        # 创建新窗口
        tmux new-window -t "$SESSION_NAME" -n "$window_name"

        # 设置窗口标题
        tmux send-keys -t "$SESSION_NAME:$window_name" \
            "echo -ne '\033]2;$window_title\007'" Enter
    done

    # 默认选中第一个窗口
    tmux select-window -t "$SESSION_NAME:agents"

    echo -e "${GREEN}✅ Dashboard已启动${NC}"
    echo -e "${BLUE}使用方法:${NC}"
    echo "  tmux attach -t $SESSION_NAME    # 连接到仪表板"
    echo "  tmux kill-session -t $SESSION_NAME  # 关闭仪表板"
}

# 设置各个窗口的监控内容
setup_windows() {
    # 1. Agent状态监控窗口
    setup_agents_window

    # 2. 任务跟踪窗口
    setup_tasks_window

    # 3. 实时事件窗口
    setup_events_window

    # 4. 系统日志窗口
    setup_logs_window

    # 5. 质量监控窗口
    setup_quality_window

    # 6. 系统状态窗口
    setup_system_window
}

# Agent状态监控
setup_agents_window() {
    local window="$SESSION_NAME:agents"

    # 分割窗口
    tmux split-window -h -t "$window"
    tmux split-window -v -t "${window}.0"
    tmux split-window -v -t "${window}.1"

    # 设置各个面板

    # 左上：Brain Agent状态
    tmux send-keys -t "${window}.0" \
        "watch -n 2 'echo \"🧠 Brain Agent Status\"; echo \"$(date)\"; \
        if [ -f $ICCC_DIR/.state/agent-status/brain.json ]; then \
            cat $ICCC_DIR/.state/agent-status/brain.json | jq .; \
        else echo \"Brain Agent 未运行\"; fi'" Enter

    # 左下：Manager Agents状态
    tmux send-keys -t "${window}.1" \
        "watch -n 3 'echo \"👨‍💼 Manager Agents\"; echo \"$(date)\"; \
        ls $ICCC_DIR/.state/agent-status/managers/*.json 2>/dev/null | \
        while read f; do echo \"\\n=== \$(basename \$f .json) ===\"; cat \$f | jq .status; done'" Enter

    # 右上：Worker Agents状态
    tmux send-keys -t "${window}.2" \
        "watch -n 3 'echo \"👷 Worker Agents\"; echo \"$(date)\"; \
        ls $ICCC_DIR/.state/agent-status/workers/*.json 2>/dev/null | \
        while read f; do echo \"\\n=== \$(basename \$f .json) ===\"; cat \$f | jq .status; done'" Enter

    # 右下：Agent统计
    tmux send-keys -t "${window}.3" \
        "watch -n 5 'echo \"📊 Agent Statistics\"; echo \"$(date)\"; \
        echo \"Brain: \$(ls $ICCC_DIR/.state/agent-status/brain.json 2>/dev/null | wc -l)\"; \
        echo \"Managers: \$(ls $ICCC_DIR/.state/agent-status/managers/*.json 2>/dev/null | wc -l)\"; \
        echo \"Workers: \$(ls $ICCC_DIR/.state/agent-status/workers/*.json 2>/dev/null | wc -l)\"; \
        echo \"Total: \$(find $ICCC_DIR/.state/agent-status/ -name \"*.json\" | wc -l)\"'" Enter
}

# 任务跟踪窗口
setup_tasks_window() {
    local window="$SESSION_NAME:tasks"

    tmux split-window -h -t "$window"
    tmux split-window -v -t "${window}.0"

    # 左上：当前任务列表
    tmux send-keys -t "${window}.0" \
        "watch -n 2 'echo \"📋 Current Tasks\"; echo \"$(date)\"; \
        if [ -f $ICCC_DIR/.state/task-states/current-tasks.json ]; then \
            cat $ICCC_DIR/.state/task-states/current-tasks.json | \
            jq -r \".[] | \\\"[\\(.status)] \\(.id): \\(.title)\\\"\"; \
        else echo \"暂无活动任务\"; fi'" Enter

    # 左下：任务统计
    tmux send-keys -t "${window}.1" \
        "watch -n 10 'echo \"📈 Task Statistics\"; echo \"$(date)\"; \
        if [ -f $ICCC_DIR/.state/task-states/task-stats.json ]; then \
            cat $ICCC_DIR/.state/task-states/task-stats.json; \
        else echo \"统计数据暂未生成\"; fi'" Enter

    # 右：任务队列
    tmux send-keys -t "${window}.2" \
        "watch -n 3 'echo \"⏳ Task Queue\"; echo \"$(date)\"; \
        redis-cli -n 1 LLEN iccc:task:queue 2>/dev/null || echo \"Redis未连接\"; \
        echo; \
        redis-cli -n 1 LRANGE iccc:task:queue 0 4 2>/dev/null | \
        jq -r \".id + \\\": \\\" + .title\" 2>/dev/null || echo \"队列中暂无任务\"'" Enter
}

# 实时事件窗口
setup_events_window() {
    local window="$SESSION_NAME:events"

    # 实时事件流
    tmux send-keys -t "$window" \
        "tail -f $ICCC_DIR/.state/events/events.log 2>/dev/null || \
        echo \"事件日志文件不存在\"; \
        echo \"按Ctrl+C退出\"" Enter
}

# 系统日志窗口
setup_logs_window() {
    local window="$SESSION_NAME:logs"

    tmux split-window -h -t "$window"

    # 左：应用日志
    tmux send-keys -t "${window}.0" \
        "tail -n 50 -f $LOG_DIR/app.log 2>/dev/null || \
        echo \"应用日志文件不存在\"" Enter

    # 右：错误日志
    tmux send-keys -t "${window}.1" \
        "tail -n 50 -f $LOG_DIR/error.log 2>/dev/null || \
        echo \"错误日志文件不存在\"" Enter
}

# 质量监控窗口
setup_quality_window() {
    local window="$SESSION_NAME:quality"

    tmux split-window -v -t "$window"

    # 上：最近的审核结果
    tmux send-keys -t "${window}.0" \
        "watch -n 10 'echo \"🔍 Recent Reviews\"; echo \"$(date)\"; \
        ls -t $ICCC_DIR/.state/quality-reviews/*.json 2>/dev/null | \
        head -5 | while read f; do \
            echo \"\\n=== \$(basename \$f .json | cut -d_ -f2) ===\"; \
            cat \$f | jq -r \'.results | to_entries[] | \
                \"[\\(.key)] \\(.value.status) (\\(.value.score // \"N/A\"))\"\' 2>/dev/null; \
        done'" Enter

    # 下：测试覆盖率趋势
    tmux send-keys -t "${window}.1" \
        "watch -n 30 'echo \"📊 Test Coverage\"; echo \"$(date)\"; \
        if [ -f $ICCC_DIR/.state/metrics/test-coverage.json ]; then \
            cat $ICCC_DIR/.state/metrics/test-coverage.json | \
            jq -r \".[] | \\\"\\(.timestamp): \\(.coverage)%\\\"\" | \
            tail -10; \
        else echo \"暂无覆盖率数据\"; fi'" Enter
}

# 系统状态窗口
setup_system_window() {
    local window="$SESSION_NAME:system"

    tmux split-window -h -t "$window"
    tmux split-window -v -t "${window}.0"
    tmux split-window -v -t "${window}.1"

    # 左上：资源使用情况
    tmux send-keys -t "${window}.0" \
        "watch -n 5 'echo \"💻 System Resources\"; echo \"$(date)\"; \
        echo \"CPU: \$(top -bn1 | grep \"Cpu(s)\" | awk \"{print \\\$2}\" | cut -d\\'%\\\" -f1)%\"; \
        echo \"Memory: \$(free -m | awk \\'NR==2{printf \"%.1f%%\", \\\$3*100/\\\$2}\\')\"; \
        echo \"Disk: \$(df -h . | awk \\'NR==2{print \\\$5}\\')\"; \
        echo \"Load: \$(uptime | awk -F\\\"load average:\\\" \\'{print \\\$2}\\')\"'" Enter

    # 左下：MongoDB状态
    tmux send-keys -t "${window}.1" \
        "watch -n 10 'echo \"🍃 MongoDB Status\"; echo \"$(date)\"; \
        mongo --eval \"db.adminCommand(\\\"ismaster\\\")\" 2>/dev/null | \
        grep \"ismaster\\\" || echo \"MongoDB未连接\"'" Enter

    # 右上：Redis状态
    tmux send-keys -t "${window}.2" \
        "watch -n 5 'echo \"🔴 Redis Status\"; echo \"$(date)\"; \
        redis-cli ping 2>/dev/null && \
        echo \"Connected clients: \$(redis-cli client list 2>/dev/null | wc -l)\" || \
        echo \"Redis未连接\"'" Enter

    # 右下：网络连接
    tmux send-keys -t "${window}.3" \
        "watch -n 10 'echo \"🌐 Network\"; echo \"$(date)\"; \
        echo \"端口 8000: \$(netstat -tlnp 2>/dev/null | grep \\\":8000\\\" | wc -l)\"; \
        echo \"端口 6379: \$(netstat -tlnp 2>/dev/null | grep \\\":6379\\\" | wc -l)\"; \
        echo \"端口 27017: \$(netstat -tlnp 2>/dev/null | grep \\\":27017\\\" | wc -l)\"'" Enter
}

# 帮助信息
show_help() {
    cat << EOF
iCCC Tmux Dashboard

用法:
  $0 [PROJECT_ROOT]    # 启动仪表板
  $0 -h               # 显示帮助

命令（在tmux会话中）:
  Ctrl+b ?            # 显示快捷键帮助
  Ctrl+b 窗口编号      # 切换窗口 (如: Ctrl+b 1)
  Ctrl+b 方向键       # 切换面板
  Ctrl+b d            # 分离会话（保持后台运行）
  Ctrl+b &            # 关闭当前窗口

重新连接:
  tmux attach -t iccc

关闭仪表板:
  tmux kill-session -t iccc

EOF
}

# 主程序
main() {
    case "$1" in
        -h|--help)
            show_help
            exit 0
            ;;
    esac

    # 初始化
    init_dashboard

    # 设置窗口内容
    setup_windows

    # 连接到会话
    echo -e "\n${BLUE}正在连接到仪表板...${NC}"
    echo -e "${YELLOW}使用 Ctrl+b d 分离会话${NC}\n"
    sleep 1
    tmux attach -t "$SESSION_NAME"
}

# 运行主程序
main "$@"