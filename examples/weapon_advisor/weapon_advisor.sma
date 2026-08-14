// weapon_advisor.sma - Example: per-player weapon advice backed by a skill.
//
// Demonstrates:
//   - genai_register_skill: gives the AI access to a skill directory loaded on
//     the sidecar, without the plugin needing to embed that knowledge itself
//   - Combining a skill with a custom tool: the AI can look up the player's
//     current loadout via get_my_weapon before giving advice
//   - this_plugin=true so weapon conversations stay separate from other plugins

#include <amxmodx>
#include <amxmodx_genai>
#include <json>

#define PLUGIN  "AI Weapon Advisor"
#define VERSION "1.0.0"
#define AUTHOR  "amxmodx-genai"

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    register_clcmd("say /weapon", "cmd_weapon");

    genai_set_plugin_context(
        "You are a Counter-Strike 1.6 weapon advisor. "
        "Use the cs16-strategy skill to answer questions about weapons and tactics. "
        "You can call get_my_weapon to check what the player currently has equipped. "
        "Keep answers to two sentences maximum."
    );

    // Register the cs16-strategy skill so the AI loads it when handling requests
    // from this plugin. The skill directory must exist at GENAI_SKILLS_PATH on
    // the sidecar host (e.g. /opt/genai/skills/weapon_advisor__cs16-strategy/).
    genai_register_skill("cs16-strategy");

    // Custom tool: what weapon is the player holding right now?
    genai_register_tool(
        "get_my_weapon",
        "Returns the name of the weapon the player currently has in their hands.",
        "tool_get_my_weapon"
    );
}

public cmd_weapon(player)
{
    if (genai_is_pending(player)) {
        client_print(player, print_chat, "[Advisor] Still thinking...");
        return PLUGIN_HANDLED;
    }

    new args[512];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);
    if (!args[0]) {
        client_print(player, print_chat, "[Advisor] Usage: /weapon <question>");
        return PLUGIN_HANDLED;
    }

    genai_query_player(player, args, "on_advisor_response", true);
    return PLUGIN_HANDLED;
}

public on_advisor_response(player, const response[], bool:is_error)
{
    if (!is_user_connected(player))
        return;

    if (is_error) {
        client_print(player, print_chat, "[Advisor] Error: %s", response);
        return;
    }

    client_print(player, print_chat, "[Advisor] %s", response);
}

public tool_get_my_weapon(player, const args_json[], result[], maxlen)
{
    if (!is_user_connected(player) || !is_user_alive(player)) {
        copy(result, maxlen, "{^"error^":^"player not alive^"}");
        return 1;
    }

    // get_user_weapon returns the weapon index; get the name via the weapon list.
    new weapon_id = get_user_weapon(player);
    new weapon_name[32];
    get_weaponname(weapon_id, weapon_name, sizeof(weapon_name) - 1);

    new esc[64];
    json_escape(weapon_name, esc, sizeof(esc) - 1);
    format(result, maxlen, "{^"weapon^":^"%s^"}", esc);
    return 1;
}

public client_disconnect(player)
{
    genai_clear_memory(player);
}
