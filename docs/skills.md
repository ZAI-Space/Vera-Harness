# Agent Skills

Put a reusable workflow in `.agents/skills/<name>/SKILL.md` in the launch directory. For a skill shared by all projects, put it under the `skills` subdirectory of the CLI's [global config directory](advanced/global_configuration.md). Each skill has YAML frontmatter and Markdown instructions.

```markdown
---
name: review-changes
description: Review a working tree and report concrete regressions.
---

Inspect the current diff, trace the changed call sites, and run the relevant tests.
For the report format, read references/report.md.
```

```bash
mini-extra skills list
mini-extra skills show review-changes
mini-extra skills show review-changes references/report.md
mini --skill review-changes -t "Review the current diff"
```

A tool-calling model can discover skills in a normal `mini` session. `skills_list` lists names and descriptions, optionally filtered by `query`. `skill_view` loads instructions or a specific attachment given by `file_path`. Pass the returned `next_offset` to continue either result. You can also use `--skill` to include one workflow in the first task message, including with text-only model adapters.

To include skills from an external catalog, such as an existing Hermes installation, add a config overlay.

```yaml
skills:
  directories:
    - ~/.hermes/skills
  disabled:
    - personal-workflow
```

Launch with `mini -c mini.yaml -c skills.yaml`. The inspection commands accept a repeatable `-d` option for additional directories. Relative roots are resolved from the launch directory. The project directory takes precedence, followed by the configured roots in order and then the global skill directory. A catalog can organize skills into nested folders. Set `skills.enabled: false` to disable discovery.

Use portable lowercase hyphenated skill names that match their directory names. Attachments are readable as UTF-8 text within `references/`, `templates/`, `scripts/`, and `assets/`. Use forward slashes in attachment paths on every platform. Keep the main instructions within 24,000 characters and put supporting detail in attachments. Reading a skill or script does not execute it or change tool permissions. Only add repositories you trust, since the agent can use their instructions to decide which tools to call.
