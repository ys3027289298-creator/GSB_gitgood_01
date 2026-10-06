# GitGood State Machine

GitGood 的虚拟仓库由五类状态组成：**工作区**（working changes）、**暂存区**
（index / staged changes）、**提交对象**（commits）、**引用**（HEAD、本地分支、
远端分支、upstream）以及 **rebase 状态**。本文档画出它们之间的合法迁移与
回滚路径，并给出异常后总能恢复一致性的状态不变量。

## 状态总览

```
                    git add <f> / git add .
  +----------------+  ------------------>  +----------------+
  |  WORKING TREE  |                       |     INDEX      |
  | (unstaged)     |  <------------------  | (staged)       |
  +----------------+   git reset [<f>]     +----------------+
         ^          (git reset --hard 同时清空两者)   |
         |                                            | git commit
         |                                            v
         |                                     +----------------+
         |                                     |    COMMITS     |
         |                                     | (对象库, 只增)  |
         |                                     +----------------+
         |                                            |
         |              git checkout / switch         v
         |                                     +----------------+
         +------------------------------------ |     REFS       |
              HEAD -> branch -> commit         | HEAD, branches,|
                                               | remote refs    |
                                               +----------------+
                                                        |
                              git rebase <onto> (冲突时) |
                                                        v
                                               +----------------+
                                               |     REBASE     |
                                               | branch / onto  |
                                               | original_sha   |
                                               | conflict files |
                                               +----------------+
```

## 合法迁移

| 迁移 | 触发命令 | 前置条件 | 状态变化 |
|---|---|---|---|
| W → I | `git add <f>` / `git add .` | 文件在工作区 | 文件移入暂存区（同一文件只保留一条暂存记录） |
| I → W | `git reset [<f>]` | 文件已暂存 | 暂存记录移回工作区（不去重则不追加） |
| W,I → ∅ | `git reset --hard` | — | 清空工作区与暂存区；rebase 中同时按 abort 回滚 |
| I → C | `git commit -m` | 暂存区非空、无 rebase | 新提交对象，当前分支指针前移，暂存区清空 |
| R → R | `git checkout <b>` / `git switch` | 目标分支存在且指向有效提交、无 rebase | HEAD 改指目标分支；失败时 HEAD 不动 |
| R → R | `git checkout -b` / `git switch -c` | 新名不存在、HEAD 有效 | 新建分支并移动 HEAD |
| R → R | `git branch` / `git branch -d` | 非当前分支、非 main、不在 rebase 中 | 增删分支引用 |
| C → C | `git merge <b>` | 源分支存在、非祖先、无 rebase | 生成双亲合并提交，当前分支前移；已包含则 "Already up to date" |
| R → R | `git push` | 分支存在 | 写入/更新 `origin/<b>` 远端引用，可设 upstream |
| R → B | `git rebase <onto>` | onto 存在、无进行中 rebase、有独有提交 | 记录 RebaseState（branch/onto/original_sha）；文件重叠则标记冲突文件进工作区 |
| B → R | `git rebase --continue` | 冲突文件已全部 `git add` | 逐条重放提交到 onto 顶端，移动分支与 HEAD，清除 rebase 状态 |
| B → R | `git rebase --abort` | rebase 进行中 | **回滚**：分支指针恢复 original_sha，HEAD 复原，清除冲突文件与暂存 |

rebase 进行中禁止 `commit / checkout / switch / merge / push / pull` 以及删除
相关分支——这些迁移在状态机中不存在，命令层直接拒绝并提示
`--continue` / `--abort`。

## 回滚路径

```
 任意失败命令                未暂存误改              暂存误改
      │                         │                      │
      ▼                         ▼                      ▼
 状态不变更（先校验后变更）   git reset --hard      git reset [<f>]

 rebase 冲突                    PR 合并失败               未知异常
      │                         │                      │
      ▼                         ▼                      ▼
 git rebase --abort      gh pr merge 自动切回        repo.recover()
 (恢复 original_sha)      原分支、PR 保持 open      (按不变量修复)
```

关键保证：

- **先校验、后变更**：`checkout`、`merge`、`rebase` 在修改任何引用前完成全部
  合法性检查，失败时状态逐字节不变。
- **rebase 记录回滚锚点**：`RebaseState.original_sha` 在 rebase 开始时保存，
  `--abort` / `reset --hard` / `recover()` 都能精确回到 rebase 前状态。
- **PR 合并是事务**：`gh pr merge` 中 checkout 或 merge 任一失败即切回原分支，
  PR 保持 open，不会留下"合并了一半"的引用。

## 状态不变量（异常后总能回到一致状态）

`VirtualRepository.check_invariant()` 逐条校验，`recover()` 负责修复：

1. HEAD 必须指向一个存在的分支，且该分支指向存在的提交。
2. 每个本地/远端分支都指向存在的提交。
3. 每个提交的父提交（含合并提交的第二父）存在或为 None。
4. 暂存区文件名无重复。
5. 工作区变更列表无重复。
6. 每个 upstream 都指向存在的远端分支。
7. rebase 状态（若存在）引用的分支与提交必须存在，且冲突文件必须仍被
   工作区或暂存区跟踪。

任何命令执行后不变量必须成立（测试 fixture 对每条命令断言）；任何未捕获
异常后 REPL 调用 `recover()`：去重暂存/工作区、清理悬空 upstream 与远端
引用、中止不可挽救的 rebase（恢复 original_sha）、摘除指向缺失提交的分支、
将 HEAD 重指到有效分支。修复后 `check_invariant()` 必为空——这就是
"总能在异常后回到一致状态"的机制保证。
