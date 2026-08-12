from amxmodx_genai.tools.native import get_all as _get_native
from amxmodx_genai.tools.plugin import make_plugin_tool

native_tools = _get_native()

__all__ = ["make_plugin_tool", "native_tools"]
