#include <amxmodx>
#include <amxmodx_genai>
#include <assert>

#define PLUGIN  "GenAI E2E Tests"
#define VERSION "1.0.0"
#define AUTHOR  "omar-hindawi98"

// Requires the real sidecar running at genai_host:genai_port.
// Tests assert protocol correctness - callbacks fire and tool round-trips
// complete. Exact LLM response text is never checked.

new bool:g_bQueryCallbackFired;
new bool:g_bToolCallbackFired;

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    genai_register_tool("test_tool", "Returns a fixed test value", "on_test_tool");

    set_task(2.0, "run_tests");
}

public run_tests()
{
    test_suite("e2e");

    test_query_response();
    test_clear_memory();
    test_tool_roundtrip();
    test_pending_flag();

    set_task(5.0, "report_results");
}

// ---- test: basic query -> response callback ----------------------------------

test_query_response()
{
    g_bQueryCallbackFired = false;
    new slot = genai_query(0, "say hello", "on_query_response");
    assert_true(slot >= 0, "query: slot allocated");
}

public on_query_response(player, const response[])
{
    g_bQueryCallbackFired = true;
    assert_int_eq(player, 0, "query response: correct player");
    assert_true(response[0] != 0, "query response: non-empty");
}

// ---- test: clear_memory does not crash ---------------------------------------

test_clear_memory()
{
    genai_clear_memory(0);
    server_print("[AMXTEST] PASS [e2e] clear_memory: no crash");
    g_iTestPassed++;
}

// ---- test: tool call round-trips through the plugin -------------------------

test_tool_roundtrip()
{
    g_bToolCallbackFired = false;
    genai_query(0, "call the test_tool with no arguments", "on_tool_query_done");
}

public on_test_tool(player, const args[], result[], maxlen)
{
    g_bToolCallbackFired = true;
    copy(result, maxlen - 1, "tool_result_value");
    return 1;
}

public on_tool_query_done(player, const response[])
{
    assert_true(response[0] != 0, "tool roundtrip: non-empty response after tool call");
}

// ---- test: is_pending flag --------------------------------------------------

test_pending_flag()
{
    genai_query(0, "check_pending", "on_pending_done");
    assert_true(genai_is_pending(0), "is_pending: true while query in flight");
}

public on_pending_done(player, const response[])
{
    assert_true(!genai_is_pending(0), "is_pending: false after callback");
}

// ---- final report -----------------------------------------------------------

public report_results()
{
    assert_true(g_bQueryCallbackFired, "query callback fired");
    assert_true(g_bToolCallbackFired,  "tool callback fired");

    test_results();
}
