// ai_testable.sma - Example plugin designed for end-to-end integration testing.
//
// The plugin uses a fixed session ("testable") so tests can target it directly.
// Every AI response and every tool call is written to the AMX log via log_amx
// so tests can grep the server log to verify end-to-end behaviour without
// needing to hook into game state.
//
// Observable side effects tests can check:
//   - Server log lines matching "[TESTABLE] response: <text>"
//   - Server log lines matching "[TESTABLE] tool_called: <name>"
//   - Server log lines matching "[TESTABLE] tool_result: <content>"
//   - The "get_log" tool the AI can call to retrieve entries via TCP wire
//
// Usage from a test:
//   1. Connect a mock AMXMODX plugin client to the sidecar via TCP.
//   2. Send a query frame with session_id="testable", tools=[get_log, set_value].
//   3. Respond to tool_call frames as this plugin would.
//   4. Read back the done frame and check the AI's final text.

#include <amxmodx>
#include <amxmodx_genai>
#include <json>

#define PLUGIN   "AI Testable Example"
#define VERSION  "1.0.0"
#define AUTHOR   "amxmodx-genai"

#define SESSION_ID    "testable"
#define MAX_LOG_LINES 64
#define MAX_LOG_LINE  256

// In-memory log that the "get_log" tool exposes to the AI.
new g_szLog[MAX_LOG_LINES][MAX_LOG_LINE];
new g_iLogCount;

// A simple key-value store the AI can read and write.
new g_szKVKey[32][64];
new g_szKVVal[32][256];
new g_iKVCount;

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    register_clcmd("say /test_ask", "cmd_test_ask");

    genai_set_plugin_context("You are a test harness assistant. You have access to tools: get_log (read the in-memory log), set_value (store a key-value pair), get_value (read a stored value). When asked to store something, call set_value. When asked what is in the log, call get_log.");

    // Tool: read the accumulated log lines.
    genai_register_tool(
        "get_log",
        "Returns all log entries recorded by this plugin since it started.",
        "tool_get_log"
    );

    // Tool: store a key-value pair (the AI can persist data back into the game).
    genai_register_tool(
        "set_value",
        "Stores a named value in the plugin's key-value store.",
        "tool_set_value"
    );
    genai_add_tool_param("key",   "string", true, "Storage key (alphanumeric, no spaces)");
    genai_add_tool_param("value", "string", true, "Value to store");

    // Tool: read a previously stored value.
    genai_register_tool(
        "get_value",
        "Retrieves a value from the plugin's key-value store.",
        "tool_get_value"
    );
    genai_add_tool_param("key", "string", true, "Storage key to look up");

    _log("plugin_init");
}

// Trigger a query to the shared "testable" session.
public cmd_test_ask(player)
{
    new args[512];
    read_args(args, sizeof(args) - 1);
    remove_quotes(args);
    if (!args[0])
        return PLUGIN_HANDLED;

    _log("query: %s", args);
    // Server-scoped session (no player index, explicit session_id, this_plugin=true).
    genai_query(args, "on_test_response", SESSION_ID, true);
    return PLUGIN_HANDLED;
}

// AI response callback (genai_query -> no player arg).
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

    // Update existing entry or append.
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
