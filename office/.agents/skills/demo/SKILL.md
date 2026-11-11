---
name: demo
description: 演示 Agent Skill 的最小结构：frontmatter + 正文 + 附件目录。
---

# Demo Skill

这是一个示例 Skill，用于演示渐进加载：

1. 启动时只把 `name` 与 `description` 注入系统提示。
2. 模型需要时调用 `loadSkill` 读取本文件正文。
3. 附件放在 `references/` 下，通过 `loadSkill(name, filename)` 读取。

## 使用步骤

- 确认目标文件路径。
- 读取附件 `references/checklist.md`。
- 按清单逐项检查并汇报结果。
