#if defined _amxgenai_core_tools_included
    #endinput
#endif
#define _amxgenai_core_tools_included

native genai_register_tool(const name[], const description[], const callback[]);
native genai_add_tool_param(const name[], const type[], bool:required, const description[]);

#include <tools/info>
#include <tools/moderation>
#include <tools/communication>
#include <tools/server>

stock register_core_tools()
{
    register_info_tools();
    register_moderation_tools();
    register_communication_tools();
    register_server_tools();
}
