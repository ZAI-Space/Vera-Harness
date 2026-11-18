"""Independent plugin management API: GitHub markets, immutable installs and runtime adaptation.

Use PluginManager for explicit user operations and load_plugins at the run boundary.
Plugins supply Skills, MCP tools and Subagent roles; they do not replace Agent Loop.
"""

from minisweagent.plugins.manager import PluginManager
from minisweagent.plugins.runtime import PluginConfig, PluginRuntime, load_plugins
from minisweagent.plugins.source import PluginError, PluginSource

__all__ = ["PluginConfig", "PluginError", "PluginManager", "PluginRuntime", "PluginSource", "load_plugins"]
