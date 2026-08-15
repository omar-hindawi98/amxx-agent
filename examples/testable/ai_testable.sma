// ai_testable.sma - Example plugin designed for end-to-end integration testing.
//
// Every plugin API function is exercised here so integration tests can verify
// each one over the wire without running a real game server.
//
// Covered natives:
//   agent_set_plugin_context        - set in plugin_init
//   agent_append_plugin_context     - append in plugin_init
//   agent_register_tool             - three tools registered
//   agent_add_tool_param            - params declared for set_value / get_value
//   agent_register_skill            - registers "testable-knowledge" skill
//   agent_query                     - server-session query (say /test_ask)
//   agent_query_player              - player-scoped query  (say /test_ask_player)
//   agent_is_pending                - checked before every query; tested via get_pending
//   agent_cancel                    - say /test_cancel
//   agent_clear_memory              - say /test_clear
//   agent_clear_longterm_memory     - say /test_clear_longterm
//
// Observable side effects tests can check:
//   [TESTABLE] response: <text>
//   [TESTABLE] tool_called: <name>
//   [TESTABLE] tool_result: <content>
//
// The matching integration test is tests/integration/test_example_testable.py.

#include <amxmodx>
#include <amxx_agent>
#include <json>

#define PLUGIN    "AI Testable Example"
#define VERSION   "1.0.0"
#define AUTHOR    "amxx-agent"

#define SESSION_ID    "testable"
#define MAX_LOG_LINES 64
#define MAX_LOG_LINE  256

// In-memory log the "get_log" tool exposes to the AI.
new g_szLog[MAX_LOG_LINES][MAX_LOG_LINE];
new g_iLogCount;

// Key-value store the AI can read and write.
new g_szKVKey[32][64];
new g_szKVVal[32][256];
new g_iKVCount;

// Tracks the queue slot returned by the last agent_query / agent_query_player
// call so that tests probing "is_pending" have a meaningful state to observe.
new g_iLastSlot;

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    register_clcmd("say /test_ask",            "cmd_test_ask");
    register_clcmd("say /test_ask_player",     "cmd_test_ask_player");
    register_clcmd("say /test_cancel",         "cmd_test_cancel");
    register_clcmd("say /test_clear",          "cmd_test_clear");
    register_clcmd("say /test_clear_longterm", "cmd_test_clear_longterm");

    // System prompt context (agent_set_plugin_context + agent_append_plugin_context).
    agent_set_plugin_context("You are a test harness assistant. Use the available tools when asked to store, retrieve, or inspect data.");
    agent_append_plugin_context("Tools: get_log (read event log), set_value (store key/value), get_value (read key/value), get_pending (check whether a query slot is pending).");

    // Register the testable-knowledge skill.
    // Skill directory: examples/testable/skills/ai_testable__testable-knowledge/
    // Deploy to AGENT_SKILLS_PATH on the sidecar host before using.
    agent_register_skill("testable-knowledge");

    // Tool: read the accumulated log lines.
    agent_register_tool(
        "get_log",
        "Returns all log entries recorded by this plugin since it started as a JSON array of strings.",
        "tool_get_log"
    );

    // Tool: store a key-value pair.
    agent_register_tool(
        "set_value",
        "Stores a named value in the plugin's key-value store.",
        "tool_set_value"
    );
    agent_add_tool_param("key",   "string", true,  "Storage key (alphanumeric, no spaces)");
    agent_add_tool_param("value", "string", true,  "Value to store");

    // Tool: read a previously stored value.
    agent_register_tool(
        "get_value",
        "Retrieves a value from the plugin's key-value store.",
        "tool_get_value"
    );
    agent_add_tool_param("key", "string", true, "Storage key to look up");

    // Tool: return whether any query slot is currently pending.
    // Tests use this to exercise agent_is_pending indirectly via the wire.
    agent_register_tool(
        "get_pending",
        "Returns whether a query is currently in-flight for the server session.",
        "tool_get_pending"
    );

    _log("plugin_init");
}

// ---- commands ---------------------------------------------------------------

// agent_query - server-scoped session (no player index, explicit session_id).
public cmd_test_ask(player)
{
    new args[512];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);
    if (!args[0])
        return PLUGIN_HANDLED;

    if (agent_is_pending(0, SESSION_ID)) {
        _log("ask_blocked: already_pending");
        return PLUGIN_HANDLED;
    }

    _log("query: %s", args);
    g_iLastSlot = agent_query(args, "on_test_response", SESSION_ID, true);
    return PLUGIN_HANDLED;
}

// agent_query_player - per-player scoped session (this_plugin=true).
public cmd_test_ask_player(player)
{
    new args[512];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);
    if (!args[0])
        return PLUGIN_HANDLED;

    if (agent_is_pending(player)) {
        _log("ask_player_blocked: already_pending player=%d", player);
        return PLUGIN_HANDLED;
    }

    _log("query_player: player=%d prompt=%s", player, args);
    g_iLastSlot = agent_query_player(player, args, "on_player_response", true);
    return PLUGIN_HANDLED;
}

// agent_cancel - cancel the in-flight server-session query.
public cmd_test_cancel(player)
{
    _log("cancel: session=%s", SESSION_ID);
    agent_cancel(0, SESSION_ID);
    return PLUGIN_HANDLED;
}

// agent_clear_memory - wipe short-term memory (triggers long-term summarization).
public cmd_test_clear(player)
{
    _log("clear_memory: session=%s", SESSION_ID);
    agent_clear_memory(0, SESSION_ID);
    return PLUGIN_HANDLED;
}

// agent_clear_longterm_memory - discard the long-term summary without summarizing.
public cmd_test_clear_longterm(player)
{
    _log("clear_longterm: session=%s", SESSION_ID);
    agent_clear_longterm_memory(0, SESSION_ID);
    return PLUGIN_HANDLED;
}

// ---- response callbacks -----------------------------------------------------

// agent_query callback - no player argument.
public on_test_response(const response[], bool:is_error)
{
    if (is_error) {
        _log("error: %s", response);
        log_amx("[TESTABLE] error: %s", response);
        return;
    }

    _log("response: %s", response);
    log_amx("[TESTABLE] response: %s", response);
}

// agent_query_player callback - receives player index.
public on_player_response(player, const response[], bool:is_error)
{
    if (is_error) {
        _log("player_error: player=%d %s", player, response);
        log_amx("[TESTABLE] player_error player=%d: %s", player, response);
        return;
    }

    _log("player_response: player=%d %s", player, response);
    log_amx("[TESTABLE] player_response player=%d: %s", player, response);
}

// ---- tools ------------------------------------------------------------------

public tool_get_log(player, const args_json[], result[], maxlen)
{
    log_amx("[TESTABLE] tool_called: get_log");
    copy(result, maxlen, "[");
    for (new i = 0; i < g_iLogCount; i++) {
        new esc[MAX_LOG_LINE * 2];
        json_escape(g_szLog[i], esc, sizeof(esc) - 1);
        if (i > 0)
            add(result, maxlen, ",");
        new entry[MAX_LOG_LINE * 2 + 4];
        format(entry, sizeof(entry) - 1, "^"%s^"", esc);
        add(result, maxlen, entry);
    }
    add(result, maxlen, "]");
    log_amx("[TESTABLE] tool_result: get_log -> %d entries", g_iLogCount);
    return 1;
}

public tool_set_value(player, const args_json[], result[], maxlen)
{
    new key[64], val[256];
    json_get_string(args_json, "key",   key, sizeof(key) - 1);
    json_get_string(args_json, "value", val, sizeof(val) - 1);

    log_amx("[TESTABLE] tool_called: set_value key=%s", key);

    if (!key[0]) {
        copy(result, maxlen, "{^"error^":^"key is empty^"}");
        return 1;
    }

    for (new i = 0; i < g_iKVCount; i++) {
        if (equal(g_szKVKey[i], key)) {
            copy(g_szKVVal[i], sizeof(g_szKVVal[]) - 1, val);
            _log("set_value: %s = %s (updated)", key, val);
            log_amx("[TESTABLE] tool_result: set_value updated key=%s", key);
            copy(result, maxlen, "{^"ok^":true,^"action^":^"updated^"}");
            return 1;
        }
    }

    if (g_iKVCount >= sizeof(g_szKVKey)) {
        copy(result, maxlen, "{^"error^":^"store full^"}");
        return 1;
    }

    copy(g_szKVKey[g_iKVCount], sizeof(g_szKVKey[]) - 1, key);
    copy(g_szKVVal[g_iKVCount], sizeof(g_szKVVal[]) - 1, val);
    g_iKVCount++;

    _log("set_value: %s = %s", key, val);
    log_amx("[TESTABLE] tool_result: set_value created key=%s", key);
    copy(result, maxlen, "{^"ok^":true,^"action^":^"created^"}");
    return 1;
}

public tool_get_value(player, const args_json[], result[], maxlen)
{
    new key[64];
    json_get_string(args_json, "key", key, sizeof(key) - 1);

    log_amx("[TESTABLE] tool_called: get_value key=%s", key);

    for (new i = 0; i < g_iKVCount; i++) {
        if (equal(g_szKVKey[i], key)) {
            new esc_key[128], esc_val[512];
            json_escape(g_szKVKey[i], esc_key, sizeof(esc_key) - 1);
            json_escape(g_szKVVal[i], esc_val, sizeof(esc_val) - 1);
            format(result, maxlen, "{^"key^":^"%s^",^"value^":^"%s^"}", esc_key, esc_val);
            log_amx("[TESTABLE] tool_result: get_value key=%s found", key);
            return 1;
        }
    }

    copy(result, maxlen, "{^"error^":^"key not found^"}");
    log_amx("[TESTABLE] tool_result: get_value key=%s not_found", key);
    return 1;
}

// Exposes agent_is_pending state to the wire so tests can verify it.
public tool_get_pending(player, const args_json[], result[], maxlen)
{
    new bool:pending = agent_is_pending(0, SESSION_ID);
    log_amx("[TESTABLE] tool_called: get_pending -> %d", pending ? 1 : 0);
    format(result, maxlen, "{^"pending^":%s}", pending ? "true" : "false");
    return 1;
}

// ---- internal log helper ----------------------------------------------------

static _log(const fmt[], any:...)
{
    if (g_iLogCount >= MAX_LOG_LINES)
        return;

    new line[MAX_LOG_LINE];
    vformat(line, sizeof(line) - 1, fmt, 2);
    copy(g_szLog[g_iLogCount], MAX_LOG_LINE - 1, line);
    g_iLogCount++;
}
