# ADR-0009: 当前任务 checkout 是 Forge 写入权限边界

Date: 2026-08-24
Status: accepted

## Context

0.15.0 隔离验收任务运行在 Codex detached worktree,Agent 却认为治理状态应该持久化到 canonical main,于是显式把 `--root` 切到真实 personalOS,打开 Run、推进 checkpoint 并创建 Observation。工作树隔离因此被模型判断绕过。

## Decision

1. 当前任务所在 Git checkout 是 Forge 命令的默认且唯一写入根。detached HEAD 不降低它的权威性。
2. 当前目录与显式 `--root` 若共享同一 Git common dir、但 top-level 不同,CLI fail closed 并说明两个路径。
3. 从其他独立仓库或非 Git 目录操作显式 Forge root 继续允许;本门禁只阻止同一仓库 sibling worktree 逃逸。
4. Packaged Skill 明确禁止因 canonical、main、detached 或持久化判断自行切换 checkout。

## Consequences

- 隔离验收即使 Agent 判断错误也不能污染真实 canonical 工作区。
- 真正需要操作 sibling worktree 时,任务必须从那个 checkout 启动;不提供方便的隐式绕过开关。
