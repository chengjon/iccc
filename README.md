本项目名称：iccc (i-claude code cli)

本项目的目标：管理/并行运行多个AI CLI实例（包括Claude Code, iflow, Gemini, Opencode等），多个AI共同协作完成同一个项目的开发工作。

工作思路：
1. 一个master cli, 用来管理全局，监控实时信息，使用最高级的model，充当大脑角色，分配工作任务。
2. 其他多个cli，可以是Claude Code, iflow, Gemini, Opencode等。运行于同一个项目目录，但有明确的工作范围和读取权限控制。
3. 工作方法：让一个Claude写代码;用另一个Claude来验证，再另一个Claude负责审核或测试。类似于与多位工程师合作（Cli使用不同的agents），有时拥有独立的背景是有益的：
4. 用Claude写代码，在另一个终端里运行/clear或启动第二个Claude，让第二个CLI审阅第一个CLI的作品；
5. 再开一个Claude（或者重新开）来阅读代码并审核反馈/clear，让这个Claude根据反馈编辑代码
6. 允许让CLI实例之间通信，给它们不同的工作草稿板，明确告诉它们写哪个、读哪个。
7. 可以使用公共数据库来管理每个cli的AI对话记录。

---

## 核心问题 (Core Questions)

1. **如何让多个CLI协作完成同一个项目的开发工作？** 多个CLI的角色除了master固定之外，其他agent如何分配（如何自动调度）？
2. **具体来说，就是多个CLI如何分工，如何协作？** 如何让他们之间通信？要不要分目录管理，每个CLI的可用工具有哪些？
3. **同一个目录下的文件夹或文件访问，读写权限控制/分配如何实现？** 在CLI间如何分配？如何处理冲突？有无优先级？
4. **CLI的对话记录如何管理？** 如何互相传递？如何记录和查询（通过API或数据库）？
5. **如何让CLI评价另一个CLI的工作，以更新方案或修改，或者给出反馈或响应？**
6. **如何监控CLI的运行状态，并给出实时反馈？**
7. **CLI 工作方式如何选择？**

---

## 初步解决方案概览 (Preliminary Solution Overview)

已在 `SOLUTION.md` 中提出了一个初步的解决方案，其核心思想是构建一个基于 **三层架构** 的多Agent系统。

**主要特点包括：**
*   **Master CLI (Opus 4):** 负责高级推理、任务分解、全局调度、冲突仲裁和质量把关。
*   **Git Worktree 隔离:** 每个Worker Agent 在独立的 Git Worktree 中工作，有效避免文件冲突。
*   **Redis 消息总线:** 实现 Agent 间的异步通信、任务队列和分布式文件锁。
*   **MongoDB 持久化:** 存储会话记录、项目状态等。
*   **Review Agent:** 专门用于代码审核和提供结构化反馈。
*   **Claude Hooks 与 WebSocket:** 构建实时可观测性系统，监控 Agent 运行状态并提供可视化 Dashboard。
*   **智能模型选择:** 根据任务复杂度动态选择 Claude 模型 (Haiku, Sonnet, Opus) 以优化成本和效率。