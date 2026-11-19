[English](../skills.md) · [简体中文](skills.md)

# Agent Skills

可复用流程放在 `.agents/skills/名称/SKILL.md`，跨项目流程放在全局配置目录的 `skills/`。文件采用 YAML frontmatter 加 Markdown 指令；名称为小写连字符且与目录一致，描述用于发现，正文按需读取。

## 发现与选择

`vera-extra skills list/show` 查看本地技能和附件；`vera --skill NAME` 把指定技能放入首条任务，也支持文本动作模型。原生工具模型可用 `skills_list` 搜索名称/描述、`skill_view` 分页读取正文/指定附件，按返回的 `next_offset` 继续。

额外根目录在 `skills.directories` 配置，可复用已有外部技能目录。优先级是项目、配置目录顺序、全局目录。CLI 的 `-d` 可重复。`disabled` 隐藏指定技能，`enabled: false` 关闭发现。嵌套分类目录可以使用，但不跨越越界链接。

## 内容与市场

主正文最多 24000 字符，附件放在 `references/ templates/ scripts/ assets/` 下，使用受支持 UTF-8 文本与正斜杠相对路径。读取脚本不会执行脚本或提升工具权限，仍需谨慎选择来源。

`vera-extra skills search/inspect/install/remove` 使用 skills.sh 与固定 GitHub 提交；`/skill search/add` 提供显式快捷入口。已安装内容通过现有发现机制生效。修改过的市场技能不会被自动删除或覆盖。见[市场](markets-and-modes.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```markdown
---
name: review-changes
description: Review a working tree and report concrete regressions.
---

Inspect the current diff, trace the changed call sites, and run the relevant tests.
For the report format, read references/report.md.
```

```bash
vera-extra skills list
vera-extra skills show review-changes
vera-extra skills show review-changes references/report.md
vera --skill review-changes -t "Review the current diff"
```

```yaml
skills:
  directories:
    - ~/.hermes/skills
  disabled:
    - personal-workflow
```
