[English](../../usage/inspector.md) · [简体中文](inspector.md)

# 轨迹查看器

Textual Inspector 浏览本地 .traj.json，不重放工具，也不需要模型。可按当前目录、单文件或目录递归打开。轨迹可能包含敏感项目内容，查看权限按本地数据处理。

q 退出，h/左与 l/右切换步骤，j/下与 k/上滚动，H/L 切换轨迹，e 用已安装的 jless 打开当前步。终端阻止文字选择时按住 Alt/Option。查看器可以显示已保存推理，但渠道/前端不应因此默认广播内部推理。实现与当前参数由下方 API 引用生成。

## 配置、命令与源码示例

```bash
vera-extra inspector
vera-extra inspector /path/to/run.traj.json
vera-extra inspector /path/to/results
```

## API 参考

::: vera.run.utilities.inspector
