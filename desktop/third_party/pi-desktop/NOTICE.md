# PI-Desktop frontend reuse

Source: https://github.com/vastsa/PI-Desktop

Reference revision: `db5dd4d0f39d66e342192f4f20a443ae56fed7f4` (local source checkout, 2026-11-19).

PI-Desktop is distributed under the GNU Lesser General Public License version 3.0. Its original license is retained in [LICENSE](LICENSE). The MIT notice retained in ../percho-LICENSE remains applicable to the original Percho code; this notice does not relicense the reused PI-Desktop code.

Adapted renderer files under `src/renderer/src/features/`:

- `plugins/PluginsPage.tsx`: page, installed groups and marketplace composition from `apps/desktop/src/pages/PluginsPage.tsx`, `features/plugins/InstalledPluginsPanel.tsx` and `MarketplacePanel.tsx`.
- `plugins/PluginDetail.tsx`: detail layout from `features/plugins/PluginDetailSheet.tsx`.
- `plugins/model.ts`: query and grouping helpers from `features/plugins/model.ts`.
- `scheduled/ScheduledPage.tsx`, `ScheduledTaskDetail.tsx`: task workspace and detail composition from `pages/ScheduledPage.tsx` and `features/scheduled/ScheduledTaskDetail.tsx`.
- `scheduled/ScheduledEditor.tsx`: calendar, interval and execution-intent editor from `features/scheduled/ScheduledEditor.tsx`.
- `scheduled/model.ts`: frontend task shapes from `packages/shared/src/types/platform.ts`.
- `../components/settings/BehaviorPanel.tsx` and `BehaviorSettingRow.tsx`: session-default composition and row layout from `features/settings/pages/AgentBehaviorSettings.tsx` and `features/settings/primitives.tsx`; excludes execution toggles and computer-use settings.
- `../components/settings/subagents/SubagentsPanel.tsx`, `SubagentEditor.tsx` and `subagent-template.ts`: list/editor composition, template-copy flow and starter instructions from `components/settings/AgentSubagentsPage.tsx` and `SubagentEditorSheet.tsx`. Rows use the existing VERA robot glyph and one-line descriptions; role fields and budgets follow Harness rather than PI-Desktop RPCs.
- `../components/settings/subagents/subagent-presets.ts`: all five preset definitions, original full prompts and declared tool lists from `packages/shared/src/subagent-presets.ts`. Template labels and compact Chinese descriptions are adapted from `packages/i18n/src/locales/zh-CN/index.ts`; create-form template switching follows `SubagentEditorSheet.tsx`. Stable preset ids are used as Harness role slugs, and original PI tool names remain draft values until the execution bridge supplies compatible tools.
- `scheduled/scheduled-format.ts`, `scheduled/scheduled-runs.ts`: reused pure helpers from the matching modules in `features/scheduled/`.

Modifications replace PI-Desktop stores, router, i18n and UI primitives with VERA equivalents. The initial extraction excluded installation and execution RPCs. VERA now supplies its own Python desktop service, module adapters and authenticated loopback transport; these do not import PI-Desktop's runtime. Unconnected preview entries remain separate from actual installed code and scheduler state. Connected template tools map to the VERA registry; unsupported browser-preview tools are not silently granted.
