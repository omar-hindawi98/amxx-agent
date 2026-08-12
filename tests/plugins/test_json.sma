#include <amxmodx>
#include <constants>
#include <json>
#include <assert>

#define PLUGIN  "GenAI JSON Tests"
#define VERSION "1.0.0"
#define AUTHOR  "omar-hindawi98"

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    test_json_escape();
    test_json_get_string();
    test_json_get_int();

    test_results();
}

// ---- json_escape ------------------------------------------------------------

test_json_escape()
{
    test_suite("json_escape");

    new out[256];

    // plain string passes through unchanged
    json_escape("hello world", out, sizeof(out));
    assert_str_eq(out, "hello world", "plain string");

    // double-quote is escaped
    json_escape(`say "hello"`, out, sizeof(out));
    assert_str_eq(out, `say \"hello\"`, "double-quote escaped");

    // backslash is escaped
    json_escape(`C:\path`, out, sizeof(out));
    assert_str_eq(out, `C:\\path`, "backslash escaped");

    // newline (char 10) becomes \n
    new src[4];
    src[0] = 'a'; src[1] = 10; src[2] = 'b'; src[3] = 0;
    json_escape(src, out, sizeof(out));
    assert_str_eq(out, `a\nb`, "newline escaped");

    // carriage return (char 13) is dropped
    new src2[4];
    src2[0] = 'a'; src2[1] = 13; src2[2] = 'b'; src2[3] = 0;
    json_escape(src2, out, sizeof(out));
    assert_str_eq(out, "ab", "CR dropped");

    // empty string
    json_escape("", out, sizeof(out));
    assert_str_eq(out, "", "empty string");
}

// ---- json_get_string --------------------------------------------------------

test_json_get_string()
{
    test_suite("json_get_string");

    new out[256];
    new ret;

    // basic flat key
    ret = json_get_string(`{"type":"query","player":"1"}`, "type", out, sizeof(out));
    assert_int_eq(ret, 1, "basic: returns 1 on found");
    assert_str_eq(out, "query", "basic: correct value");

    // second key
    ret = json_get_string(`{"type":"query","player":"1"}`, "player", out, sizeof(out));
    assert_int_eq(ret, 1, "second key: returns 1");
    assert_str_eq(out, "1", "second key: correct value");

    // key not present
    ret = json_get_string(`{"type":"query"}`, "name", out, sizeof(out));
    assert_int_eq(ret, 0, "missing key: returns 0");

    // escaped quote inside value
    ret = json_get_string(`{"text":"say \"hi\""}`, "text", out, sizeof(out));
    assert_int_eq(ret, 1, "escaped quote: returns 1");
    assert_str_eq(out, `say "hi"`, "escaped quote: unescaped in output");

    // escaped backslash inside value
    ret = json_get_string(`{"path":"C:\\\\Maps"}`, "path", out, sizeof(out));
    assert_int_eq(ret, 1, "escaped backslash: returns 1");
    assert_str_eq(out, `C:\\Maps`, "escaped backslash: correct value");

    // escaped newline inside value
    ret = json_get_string(`{"msg":"line1\\nline2"}`, "msg", out, sizeof(out));
    assert_int_eq(ret, 1, "escaped newline: returns 1");
    new expected[16];
    expected[0] = 'l'; expected[1] = 'i'; expected[2] = 'n'; expected[3] = 'e';
    expected[4] = '1'; expected[5] = 10; expected[6] = 'l'; expected[7] = 'i';
    expected[8] = 'n'; expected[9] = 'e'; expected[10] = '2'; expected[11] = 0;
    assert_str_eq(out, expected, "escaped newline: decoded in output");

    // empty value
    ret = json_get_string(`{"system":""}`, "system", out, sizeof(out));
    assert_int_eq(ret, 1, "empty value: returns 1");
    assert_str_eq(out, "", "empty value: empty output");

    // value with spaces
    ret = json_get_string(`{"prompt":"what to buy?"}`, "prompt", out, sizeof(out));
    assert_str_eq(out, "what to buy?", "spaces in value");

    // tool_result message type (matches real protocol)
    ret = json_get_string(
        `{"type":"tool_result","id":"plug_ab12cd34","content":"de_dust2"}`,
        "id", out, sizeof(out));
    assert_str_eq(out, "plug_ab12cd34", "tool_result id");

    ret = json_get_string(
        `{"type":"tool_result","id":"plug_ab12cd34","content":"de_dust2"}`,
        "content", out, sizeof(out));
    assert_str_eq(out, "de_dust2", "tool_result content");
}

// ---- json_get_int -----------------------------------------------------------

test_json_get_int()
{
    test_suite("json_get_int");

    // basic integer
    new val = json_get_int(`{"player":3}`, "player");
    assert_int_eq(val, 3, "basic integer");

    // zero
    val = json_get_int(`{"player":0}`, "player");
    assert_int_eq(val, 0, "zero");

    // larger number
    val = json_get_int(`{"port":27016}`, "port");
    assert_int_eq(val, 27016, "larger number");

    // integer among string fields
    val = json_get_int(`{"type":"query","player":7,"tools":[]}`, "player");
    assert_int_eq(val, 7, "integer among string fields");

    // missing key returns 0
    val = json_get_int(`{"type":"query"}`, "player");
    assert_int_eq(val, 0, "missing key returns 0");

    // whitespace after colon
    val = json_get_int(`{"player": 5}`, "player");
    assert_int_eq(val, 5, "whitespace after colon");
}
