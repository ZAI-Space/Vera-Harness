[English](../../advanced/v2_migration.md) · [简体中文](v2_migration.md)

# 命名兼容与迁移

VERA 使用当前发行包、命令和 Python 命名。安装本仓库并确认活动虚拟环境，新旧包并存时先核对实际加载路径；不要从上游安装命令误装另一项目。

## 已有使用方式

正式包/导入使用 `vera`，入口为 `vera`、`vera-extra`、`python -m vera`；旧 Python 导入 `minisweagent.*` 和自定义类路径需要更新。旧 mini 系列命令保留为已安装别名。默认文件为 `vera.yaml`、`vera_textbased.yaml`，旧内置短文件名仅作查找兼容。变量用 `VERA_*`，默认配置覆盖用 `VERA_CONFIG_PATH`；没有新键时读取历史 `MSWEA_*`。

新配置使用 VERA 目录；仅有旧配置目录时继续读取，显式 VERA_GLOBAL_CONFIG_DIR 优先，不自动移动或删除用户数据。Git 缓存也可复用。新轨迹写 `vera_version` 与 `vera-1.1`，旧轨迹结构仍可查看，历史运行仍可查询；恢复时仅规范化已知旧包名前缀，执行配置、工作区和收据仍须通过校验。未知自定义类或执行配置变化可能需要核对原收据后新建任务。保留第三方版权不等于继续使用上游品牌。

原生工具调用为主路径，文本动作适配器仅 Bash。完成标记保持 COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT，流程异常位于当前 exceptions 模块，run 返回 exit metadata，配置使用 Pydantic。Responses 短名是 litellm_response，不是过期的 *_toolcall 别名。旧 -v 界面、已移除 issue runner 和 --config-class 不能视为现有功能。

## 应用准备

前端按公开 Python 接口/状态对接，不根据终端品牌文字或随意改 Schema 来推断协议。聊天 session_id 与私有存储位置显式选择，未知工具结果先核实再恢复。见[前端对接](../frontend-integration.md)。

## 配置、命令与源码示例

示例与英文版保持同一调用契约；按环境替换占位参数，标识符保留源码命名。

```bash
python -m pip install -e '.[mcp,channels]'
vera --help
vera-extra --help
```

```python
from vera.exceptions import FormatError, Submitted
```
