from amxx_agent.tools.native import get_all as _get_native
from amxx_agent.tools.plugin import make_plugin_tool

native_tools = _get_native()

__all__ = ["make_plugin_tool", "native_tools"]
