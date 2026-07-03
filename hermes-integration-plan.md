# iCCC + Hermes 集成方案

> 目标：Hermes 作为 Brain，iCCC 作为协作底座，建立标准化开发流水线

---

## 现有能力（iCCC 已具备）

| 组件 | iCCC 位置 | 状态 |
|------|-----------|------|
| HTN 任务分解 | `iccc/planning/htn.py` | ✅ 13 种预定义方法 |
| STRIPS 规划 | `iccc/planning/strips.py` | ✅ A* 搜索 |
| 自适应重规划 | `iccc/planning/adaptive.py` | ✅ 7 种失败模式 |
| Redis 事件总线 | Redis Streams | ✅ 已在运行 |
| Git Worktree | `iccc/` | ✅ 已实现 |
| REST API | 端口 8000 | ✅ 22+ 接口 |
| 代理模板 | `iccc/agents/templates/` | ✅ 4 种内置 |
| 测试 | `tests/` | 960+ ✅ |
| 多 CLI 架构 | `iCCC_multi_CLI_architecture_analysis.md` | ✅ 设计文档 |

## 集成方式（不修改 iCCC 源码）

Hermes 通过 REST API 和 Redis 与 iCCC 通信，不需要修改 iccc 自身代码。

```
你（开发者） → Hermes（Brain）
                  │
          ┌───────┴───────┐
          │               │
    iCCC REST API    iCCC Redis Bus
    (规划/任务)       (通知)
          │               │
          └───────┬───────┘
                  │
         ┌────────┴────────┐
         │                 │
    Worktree-A        Worktree-B
    (Claude Code)    (OpenCode)
```

## 第一步：验证核心链路

先跑通最简链路：Hermes → iCCC 规划 → 建 worktree → 分派任务 → 完成

1. Hermes 通过 iCCC API 创建项目
2. Hermes 用 HTN 分解一个简单任务
3. Hermes 创建 worktree
4. Hermes 通知其他 CLI
5. 完成后合并

要不要先从第一步开始？
