# INSTITUTION (The Law)

本文档是项目的**最高规范**。
所有的代码、架构和流程都必须严格遵守本文档的规定。
只有 Brain Agent 有权限修改本文档。

## 1. 架构原则
- **Think First**: 必须先思考，后行动。
- **Spec Driven**: 一切开发以文档为准。
- **Isolation**: Agent 必须在独立工作区工作。

## 2. 编码规范
- **Python**: 遵循 PEP 8，使用 Type Hints (MyPy Strict)。
- **Docstrings**: 所有公共函数必须包含 Google Style 文档字符串。
- **Testing**: 必须包含 Pytest 单元测试。

## 3. 安全规定
- 禁止硬编码密钥。
- 禁止执行高危系统命令 (rm -rf / 等)。
- 依赖包必须锁定版本。

## 4. Git 协作规范
- 禁止直推 `main`/`master` 分支。
- Commit Message 必须遵循 Conventional Commits (feat:, fix:, docs: 等)。
