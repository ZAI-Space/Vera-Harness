---
name: review
description: Review the assigned code change and report actionable correctness defects.
---

Read the requested diff, changed functions and their callers. Check error paths,
state changes and boundary cases. Report only defects supported by concrete code
or a reproducible failing command. Include the affected file and line, impact and
a minimal correction. If no verified defect is found, say so and list untested scope.
Do not edit files unless the user explicitly requests a fix. Bash access is not a
read-only security boundary; follow the task's authorization.
