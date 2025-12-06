<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**iCCC (i-Claude Code CLI)** is a multi-agent orchestration system for managing and running multiple AI CLI instances (Claude Code, iflow, Gemini, Opencode) in parallel to collaboratively complete software development tasks.

**Current State:** Design/specification phase - comprehensive documentation exists but no implementation code yet.

## Architecture

### Multi-Agent Paradigm

```
Master CLI (Orchestrator/Meta-Agent)
    │  Uses Claude Opus for high-level reasoning
    │  Breaks down complex tasks into parallel subtasks
    ▼
Task Queue (Redis-based)
    │
    ├──► Worker Agent 1 (Frontend - Haiku)
    ├──► Worker Agent 2 (Backend - Sonnet)
    ├──► Worker Agent 3 (Testing - Sonnet)
    └──► Worker Agent N (Docs - Haiku)
```

### Key Components

1. **Master CLI**: Central intelligence using Claude Opus - decomposes tasks, assigns work, monitors progress
2. **Worker CLIs**: Specialized agents with explicit read/write permissions, isolated via Git worktrees
3. **Claude Hooks**: PreToolUse (safety), PostToolUse (logging), Notification, Stop, SubagentStop
4. **Observability**: Real-time dashboard with WebSocket streaming, AI-powered summaries

### Model Selection Strategy

- **Haiku 3.5**: Fast, cheap - simple tasks, file operations
- **Sonnet 4**: Balanced - general coding, refactoring
- **Opus 4**: Complex architecture, critical work

## Planned Technology Stack

| Layer | Technology |
|-------|-----------|
| Orchestrator | Python |
| API | Litestar (ASGI) |
| Primary DB | MongoDB |
| Queue/Cache | Redis |
| Events DB | SQLite |
| Dashboard | Vue.js + WebSockets |
| Desktop App | Dioxus (Rust) |
| Isolation | Git worktrees, Docker |

## Data Model (Core Entities)

- **Project**: UUID, name, directory, status, metadata
- **Agent**: ID, type, model, specialization, status, worktree_path
- **Task**: UUID, project_id, description, type, status, dependencies, assigned_agent_id
- **Session**: UUID, agent_id, messages[], token_usage
- **Event**: timestamp, session_id, event_type, data (JSON)

## API Endpoints (Planned)

- `/projects` - Project CRUD
- `/agents` - Agent registration, status, task assignment
- `/tasks` - Task creation, status updates, queue access
- `/events` - Hook event ingestion
- `/ws` - WebSocket for real-time dashboard

## Conflict Prevention

1. **Git Worktrees**: Each agent works in isolated checkout
2. **Redis File Locks**: Exclusive locks before file modification
3. **Dependency Analysis**: Task scheduling respects file dependencies

## Planning Systems

The orchestrator uses concepts from:
- **STRIPS**: State-space planning with preconditions/effects
- **A\* Search**: Optimal pathfinding through task space
- **HTN**: Hierarchical task decomposition

## Documentation Structure

- `README.md` - Project overview (Chinese)
- `development_document.md` - Complete technical specification
- `docs/` - Educational guides on:
  - Running parallel AI agents
  - Git worktrees for agent isolation
  - Claude Hooks for safety/observability
  - Planning algorithms
  - Model selection and rate limits
