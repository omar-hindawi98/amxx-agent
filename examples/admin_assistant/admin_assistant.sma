// admin_assistant.sma - Example: admin-only AI assistant with persistent memory
// and access to core server tools (get_players, get_player_info, kick, ban, etc.).
//
// Demonstrates:
//   - Access control: only players with ADMIN_KICK can use the assistant
//   - Per-admin memory isolated to this plugin (this_plugin=true)
//   - genai_set_plugin_context + genai_append_plugin_context together
//   - genai_clear_memory via an explicit reset command
//   - Letting the AI use core tools without registering them manually
//     (registered by the core plugin when genai_core_tools=1)

#include <amxmodx>
#include <amxmodx_genai>

#define PLUGIN  "AI Admin Assistant"
#define VERSION "1.0.0"
#define AUTHOR  "amxmodx-genai"

#define REQUIRED_ACCESS ADMIN_KICK

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    register_clcmd("say /ai",       "cmd_ai");
    register_clcmd("say /ai_reset", "cmd_ai_reset");
    register_concmd("amx_ai",       "cmd_ai", REQUIRED_ACCESS);

    genai_set_plugin_context("You are an AI assistant for server administrators on a Counter-Strike 1.6 server. Use the available tools to look up players, check server state, or take moderation actions. Always confirm destructive actions (kick, ban) before executing them.");

    // Append live server info so the AI has it in every conversation.
    new map[36];
    get_mapname(map, sizeof(map) - 1);

    new ctx[128];
    format(ctx, sizeof(ctx) - 1,
        "Current map: %s. Max players: %d.", map, get_maxplayers());
    genai_append_plugin_context(ctx);
}

public cmd_ai(player)
{
    if (!(get_user_flags(player) & REQUIRED_ACCESS)) {
        client_print(player, print_chat, "[AI] Access denied.");
        return PLUGIN_HANDLED;
    }

    if (genai_is_pending(player)) {
        client_print(player, print_chat, "[AI] Still working on your last request...");
        return PLUGIN_HANDLED;
    }

    new args[512];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);
    if (!args[0]) {
        client_print(player, print_chat, "[AI] Usage: /ai <question>  or  amx_ai <question>");
        return PLUGIN_HANDLED;
    }

    genai_query_player(player, args, "on_ai_response", true);
    client_print(player, print_chat, "[AI] Thinking...");
    return PLUGIN_HANDLED;
}

public cmd_ai_reset(player)
{
    if (!(get_user_flags(player) & REQUIRED_ACCESS)) {
        client_print(player, print_chat, "[AI] Access denied.");
        return PLUGIN_HANDLED;
    }

    genai_clear_memory(player);
    client_print(player, print_chat, "[AI] Conversation cleared.");
    return PLUGIN_HANDLED;
}

public on_ai_response(player, const response[], bool:is_error)
{
    if (!is_user_connected(player))
        return;

    if (is_error) {
        client_print(player, print_chat, "[AI] Error: %s", response);
        return;
    }

    // Chat has a ~128 char limit per message; split long responses.
    new total = strlen(response);
    new offset = 0;
    new chunk[120];

    while (offset < total) {
        new len = min(sizeof(chunk) - 1, total - offset);
        // Break on a word boundary when possible.
        if (offset + len < total) {
            new cut = len - 1;
            while (cut > 0 && response[offset + cut] != ' ')
                cut--;
            if (cut > 0)
                len = cut;
        }
        for (new c = 0; c < len; c++)
            chunk[c] = response[offset + c];
        chunk[len] = 0;
        client_print(player, print_chat, "[AI] %s", chunk);
        offset += len;
        if (offset < total && response[offset] == ' ')
            offset++;
    }
}

public client_disconnect(player)
{
    if (get_user_flags(player) & REQUIRED_ACCESS)
        genai_clear_memory(player);
}
