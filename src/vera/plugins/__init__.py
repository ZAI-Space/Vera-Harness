"""Independent plugin management API: GitHub markets, immutable installs and runtime adaptation.

Use PluginManager for explicit user operations and load_plugins at the run boundary.
Plugins supply Skills, MCP tools and Subagent roles; they do not replace Agent Loop.
"""

from vera.plugins.manager import PluginManager
from vera.plugins.runtime import PluginConfig, PluginRuntime, load_plugins
from vera.plugins.source import PluginError, PluginSource

__all__ = ["PluginConfig", "PluginError", "PluginManager", "PluginRuntime", "PluginSource", "load_plugins"]
