// admin_assistant.sma - Example: admin-only AI assistant.
//
// Demonstrates every major plugin API function:
//   - genai_set_plugin_context + genai_append_plugin_context
//   - genai_register_tool + genai_add_tool_param  (get_server_stats, set_motd)
//   - genai_register_skill                         (admin-procedures skill)
//   - genai_query_player                           (per-admin memory, this_plugin=true)
//   - genai_is_pending                             (guard duplicate requests)
//   - genai_cancel                                 (/ai_cancel command)
//   - genai_clear_memory                           (/ai_reset command)
//   - genai_clear_longterm_memory                  (amx_ai_fullreset console command)

#include <amxmodx>
#include <amxmodx_genai>
#include <json>

#define PLUGIN  "AI Admin Assistant"
#define VERSION "1.0.0"
#define AUTHOR  "amxmodx-genai"

#define REQUIRED_ACCESS ADMIN_KICK

// Persistent MOTD text the AI can update via the set_motd tool.
new g_szMotd[512];

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    register_clcmd("say /ai",          "cmd_ai");
    register_clcmd("say /ai_cancel",   "cmd_ai_cancel");
    register_clcmd("say /ai_reset",    "cmd_ai_reset");
    register_concmd("amx_ai_fullreset","cmd_ai_fullreset", REQUIRED_ACCESS,
                    "Wipe long-term AI memory for an admin (amx_ai_fullreset <#id>)");

    // Base system prompt for this plugin.
    genai_set_plugin_context("You are an AI assistant for server administrators on a Counter-Strike 1.6 server. Use the available tools to check server state and take moderation actions. Always confirm before kicking or banning a player.");

    // Append live context that applies to every conversation.
    new map[36];
    get_mapname(map, sizeof(map) - 1);
    new ctx[256];
    format(ctx, sizeof(ctx) - 1,
        "Current map: %s. Max players: %d. You have tools: get_server_stats and set_motd.",
        map, get_maxplayers());
    genai_append_plugin_context(ctx);

    // Register the admin-procedures skill.
    // Deploy examples/admin_assistant/skills/admin_assistant__admin-procedures/
    // to GENAI_SKILLS_PATH on the sidecar host before starting it.
    genai_register_skill("admin-procedures");

    // Tool: return a JSON snapshot of current server state.
    genai_register_tool(
        "get_server_stats",
        "Returns current player count, map name, and server uptime in seconds.",
        "tool_get_server_stats"
    );
    // No parameters - the tool takes none.

    // Tool: update the server MOTD text.
    genai_register_tool(
        "set_motd",
        "Replaces the server message-of-the-day with the provided text.",
        "tool_set_motd"
    );
    genai_add_tool_param("text", "string", true, "New MOTD text (plain text, max 480 chars)");
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
        client_print(player, print_chat, "[AI] Usage: /ai <question>  |  /ai_cancel  |  /ai_reset");
        return PLUGIN_HANDLED;
    }

    genai_query_player(player, args, "on_ai_response", true);
    client_print(player, print_chat, "[AI] Thinking...");
    return PLUGIN_HANDLED;
}

// Cancel an in-flight query without waiting for the response.
public cmd_ai_cancel(player)
{
    if (!(get_user_flags(player) & REQUIRED_ACCESS)) {
        client_print(player, print_chat, "[AI] Access denied.");
        return PLUGIN_HANDLED;
    }

    genai_cancel(player);
    client_print(player, print_chat, "[AI] Request cancelled.");
    return PLUGIN_HANDLED;
}

// Clear short-term memory (triggers long-term summarization on the sidecar).
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

// Wipe both short-term AND long-term memory for the target player.
// Usage: amx_ai_fullreset <#id|name>
public cmd_ai_fullreset(player, level, cid)
{
    if (!cmd_access(player, level, cid, 2))
        return PLUGIN_HANDLED;

    new arg[32];
    read_argv(1, arg, sizeof(arg) - 1);
    new target = cmd_target(player, arg, CMDTARGET_ALLOW_SELF);
    if (!target)
        return PLUGIN_HANDLED;

    // genai_clear_memory triggers summarization then deletes short-term turns.
    // genai_clear_longterm_memory then discards the resulting summary.
    genai_clear_memory(target);
    genai_clear_longterm_memory(target);

    new name[32];
    get_user_name(target, name, sizeof(name) - 1);
    client_print(player, print_console, "[AI] Full memory reset done for %s.", name);
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

    // Chat has a ~128 char limit per message; split long responses on word boundaries.
    new total = strlen(response);
    new offset = 0;
    new chunk[120];

    while (offset < total) {
        new len = min(sizeof(chunk) - 1, total - offset);
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

// ---- tools ------------------------------------------------------------------

public tool_get_server_stats(player, const args_json[], result[], maxlen)
{
    new map[36];
    get_mapname(map, sizeof(map) - 1);

    new esc_map[72];
    json_escape(map, esc_map, sizeof(esc_map) - 1);

    new connected = 0;
    new maxp = get_maxplayers();
    for (new i = 1; i <= maxp; i++) {
        if (is_user_connected(i))
            connected++;
    }

    format(result, maxlen,
        "{^"players^":%d,^"max_players^":%d,^"map^":^"%s^"}",
        connected, maxp, esc_map);
    return 1;
}

public tool_set_motd(player, const args_json[], result[], maxlen)
{
    new text[512];
    json_get_string(args_json, "text", text, sizeof(text) - 1);

    if (!text[0]) {
        copy(result, maxlen, "{^"error^":^"text is empty^"}");
        return 1;
    }

    copy(g_szMotd, sizeof(g_szMotd) - 1, text);
    // In a real server: show_motd or write to a file here.

    copy(result, maxlen, "{^"ok^":true}");
    return 1;
}

public client_disconnect(player)
{
    if (get_user_flags(player) & REQUIRED_ACCESS) {
        genai_cancel(player);
        genai_clear_memory(player);
    }
}
