#include <amxmodx>
#include <sockets>
#include <constants>
#include <json>
#include <queue>

#define PLUGIN  "GenAI Core"
#define VERSION "2.0.0" // {x-release-please-version}
#define AUTHOR  "omar-hindawi98"

// ---- cvars ------------------------------------------------------------------

new g_pCvarHost;
new g_pCvarPort;

// ---- plugin lifecycle -------------------------------------------------------

public plugin_init()
{
    register_plugin(PLUGIN, VERSION, AUTHOR);

    g_pCvarHost = register_cvar("genai_host", "127.0.0.1");
    g_pCvarPort = register_cvar("genai_port", "27016");

    g_tSystemPrompts = TrieCreate();

    register_library("amxmodx_genai");

    register_native("genai_query",                 "native_query");
    register_native("genai_cancel",                "native_cancel");
    register_native("genai_is_pending",            "native_is_pending");
    register_native("genai_set_plugin_context",    "native_set_plugin_context");
    register_native("genai_append_plugin_context", "native_append_plugin_context");
    register_native("genai_clear_memory",           "native_clear_memory");
    register_native("genai_register_tool",         "native_register_tool");
    register_native("genai_add_tool_param",        "native_add_tool_param");
    register_native("genai_register_skill",        "native_register_skill");

    for (new i = 0; i < MAX_QUEUE; i++)
        g_iQueueSocket[i] = -1;

    set_task(0.1, "task_poll_sockets");
}

public plugin_end()
{
    for (new i = 0; i < MAX_QUEUE; i++)
        if (g_bQueueUsed[i])
            free_slot(i);
    TrieDestroy(g_tSystemPrompts);
}

// ---- socket poll ------------------------------------------------------------

static bool:dispatch_message(i, const line[])
{
    new msg_type[16];
    json_get_string(line, "type", msg_type, sizeof(msg_type) - 1);

    if (equal(msg_type, "tool_call")) {
        new tool_id[48];
        new tool_name[MAX_TOOL_NAME];
        new tool_args[MAX_RESPONSE];

        json_get_string(line, "id",   tool_id,   sizeof(tool_id)   - 1);
        json_get_string(line, "name", tool_name, sizeof(tool_name) - 1);
        json_get_string(line, "args", tool_args, sizeof(tool_args) - 1);

        new result[MAX_RESPONSE];
        new found = 0;
        for (new t = 0; t < g_iToolCount; t++) {
            if (equal(g_szToolName[t], tool_name)) {
                callfunc_begin(g_szToolCallback[t], g_szToolPlugin[t]);
                callfunc_push_int(g_iQueuePlayer[i]);
                callfunc_push_str(tool_args);
                callfunc_push_str(result);
                callfunc_push_int(MAX_RESPONSE - 1);
                callfunc_end();
                found = 1;
                break;
            }
        }

        if (!found)
            copy(result, MAX_RESPONSE - 1, "(tool not found)");

        new escaped_id[96];
        new escaped_result[MAX_RESPONSE * 2];
        json_escape(tool_id,  escaped_id,     sizeof(escaped_id)     - 1);
        json_escape(result,   escaped_result, sizeof(escaped_result) - 1);

        new reply[MAX_RESPONSE * 2 + 64];
        format(reply, sizeof(reply) - 1,
            "{^"type^":^"tool_result^",^"id^":^"%s^",^"content^":^"%s^"}^n",
            escaped_id, escaped_result);
        socket_send_str(g_iQueueSocket[i], reply);

    } else if (equal(msg_type, "response")) {
        new text[MAX_RESPONSE];
        json_get_string(line, "text", text, sizeof(text) - 1);
        copy(g_szQueueResponse[i], MAX_RESPONSE - 1, text);

    } else if (equal(msg_type, "done")) {
        callfunc_begin(g_szQueueCallback[i], g_szQueuePlugin[i]);
        callfunc_push_int(g_iQueuePlayer[i]);
        callfunc_push_str(g_szQueueResponse[i]);
        callfunc_end();

        free_slot(i);
        return true;
    }

    return false;
}

public task_poll_sockets()
{
    for (new i = 0; i < MAX_QUEUE; i++) {
        if (!g_bQueueUsed[i])
            continue;

        if (!socket_is_readable(g_iQueueSocket[i], 0))
            continue;

        new chunk[512];
        new bytes = socket_recv(g_iQueueSocket[i], chunk, sizeof(chunk) - 1);

        if (bytes <= 0) {
            callfunc_begin(g_szQueueCallback[i], g_szQueuePlugin[i]);
            callfunc_push_int(g_iQueuePlayer[i]);
            callfunc_push_str("(AI connection dropped)");
            callfunc_end();
            free_slot(i);
            continue;
        }

        new buf_space = MAX_RESPONSE - g_iQueueBufLen[i] - 1;
        if (bytes > buf_space)
            bytes = buf_space;

        for (new c = 0; c < bytes; c++)
            g_szQueueBuf[i][g_iQueueBufLen[i] + c] = chunk[c];
        g_iQueueBufLen[i] += bytes;
        g_szQueueBuf[i][g_iQueueBufLen[i]] = 0;

        new nl;
        while ((nl = strfind(g_szQueueBuf[i], "^n")) != -1) {
            new line[MAX_RESPONSE];
            new copy_len = (nl < MAX_RESPONSE - 1) ? nl : MAX_RESPONSE - 2;
            for (new c = 0; c < copy_len; c++)
                line[c] = g_szQueueBuf[i][c];
            line[copy_len] = 0;

            new remaining = g_iQueueBufLen[i] - nl - 1;
            for (new c = 0; c < remaining; c++)
                g_szQueueBuf[i][c] = g_szQueueBuf[i][nl + 1 + c];
            g_iQueueBufLen[i] = remaining;
            g_szQueueBuf[i][remaining] = 0;

            if (dispatch_message(i, line))
                break;
        }
    }

    set_task(0.1, "task_poll_sockets");
}

// ---- natives ----------------------------------------------------------------

public native_query(plugin_id, num_params)
{
    new player = get_param(1);

    new prompt[MAX_PROMPT];
    get_string(2, prompt, MAX_PROMPT - 1);

    new callback[MAX_CALLBACK];
    get_string(3, callback, MAX_CALLBACK - 1);

    // optional session_id - defaults to player index string
    new session_id[MAX_SESSION_ID];
    if (num_params >= 4)
        get_string(4, session_id, MAX_SESSION_ID - 1);
    if (!session_id[0])
        num_to_str(player, session_id, MAX_SESSION_ID - 1);

    new slot = find_free_slot();
    if (slot == -1) {
        log_amx("[GenAI] queue full, dropping request for session %s", session_id);
        return -1;
    }

    new host[64];
    get_pcvar_string(g_pCvarHost, host, 63);
    new port = get_pcvar_num(g_pCvarPort);

    new err;
    new sock = socket_open(host, port, SOCKET_TCP, err);
    if (sock == -1 || err != 0) {
        sock = socket_open(host, port, SOCKET_TCP, err);
        if (sock == -1 || err != 0) {
            log_amx("[GenAI] socket_open failed after retry (err %d)", err);
            return -1;
        }
        log_amx("[GenAI] socket_open succeeded on retry");
    }

    new plugin_filename[MAX_PLUGIN_NAME];
    get_plugin(plugin_id, plugin_filename, MAX_PLUGIN_NAME - 1);

    new system_prompt[MAX_SYSTEM];
    TrieGetString(g_tSystemPrompts, plugin_filename, system_prompt, MAX_SYSTEM - 1);

    new tools_json[MAX_TOOLS * (MAX_TOOL_NAME + MAX_TOOL_DESC + MAX_TOOL_PARAMS_JSON + 48)];
    copy(tools_json, sizeof(tools_json) - 1, "[");
    for (new t = 0; t < g_iToolCount; t++) {
        new escaped_name[MAX_TOOL_NAME * 2];
        new escaped_desc[MAX_TOOL_DESC * 2];
        json_escape(g_szToolName[t], escaped_name, sizeof(escaped_name) - 1);
        json_escape(g_szToolDesc[t], escaped_desc, sizeof(escaped_desc) - 1);

        new entry[MAX_TOOL_NAME * 2 + MAX_TOOL_DESC * 2 + MAX_TOOL_PARAMS_JSON + 48];
        format(entry, sizeof(entry) - 1,
            "%s{^"name^":^"%s^",^"description^":^"%s^",^"params^":%s}",
            (t > 0) ? "," : "",
            escaped_name, escaped_desc, g_szToolParamsJson[t]);
        add(tools_json, sizeof(tools_json) - 1, entry);
    }
    add(tools_json, sizeof(tools_json) - 1, "]");

    new skills_json[MAX_SKILLS * (MAX_SKILL_NAME * 2 + 4)];
    copy(skills_json, sizeof(skills_json) - 1, "[");
    for (new s = 0; s < g_iSkillCount; s++) {
        new escaped_skill[MAX_SKILL_NAME * 2];
        json_escape(g_szSkillName[s], escaped_skill, sizeof(escaped_skill) - 1);
        new entry[MAX_SKILL_NAME * 2 + 8];
        format(entry, sizeof(entry) - 1, "%s^"%s^"", (s > 0) ? "," : "", escaped_skill);
        add(skills_json, sizeof(skills_json) - 1, entry);
    }
    add(skills_json, sizeof(skills_json) - 1, "]");

    // Strip .amxx to get a clean plugin name for the system prompt section heading.
    new plugin_name[MAX_PLUGIN_NAME];
    copy(plugin_name, MAX_PLUGIN_NAME - 1, plugin_filename);
    new ext2 = strfind(plugin_name, ".amxx");
    if (ext2 != -1)
        plugin_name[ext2] = 0;

    new escaped_prompt[MAX_PROMPT * 2];
    new escaped_system[MAX_SYSTEM * 2];
    new escaped_session[MAX_SESSION_ID * 2];
    new escaped_plugin[MAX_PLUGIN_NAME * 2];
    json_escape(prompt,        escaped_prompt,  sizeof(escaped_prompt)  - 1);
    json_escape(system_prompt, escaped_system,  sizeof(escaped_system)  - 1);
    json_escape(session_id,    escaped_session, sizeof(escaped_session) - 1);
    json_escape(plugin_name,   escaped_plugin,  sizeof(escaped_plugin)  - 1);

    new request[MAX_PROMPT * 2 + MAX_SYSTEM * 2 + MAX_TOOLS * (MAX_TOOL_NAME + MAX_TOOL_DESC + MAX_TOOL_PARAMS_JSON + 48) + MAX_SKILLS * (MAX_SKILL_NAME * 2 + 4) + 256];
    format(request, sizeof(request) - 1,
        "{^"type^":^"query^",^"player^":%d,^"session_id^":^"%s^",^"prompt^":^"%s^",^"plugin^":^"%s^",^"system^":^"%s^",^"tools^":%s,^"skills^":%s}^n",
        player, escaped_session, escaped_prompt, escaped_plugin, escaped_system, tools_json, skills_json);

    socket_send(sock, request, strlen(request));

    g_bQueueUsed[slot]         = true;
    g_iQueuePlayer[slot]       = player;
    g_iQueueSocket[slot]       = sock;
    g_iQueueBufLen[slot]       = 0;
    g_szQueueBuf[slot][0]      = 0;
    g_szQueueResponse[slot][0] = 0;
    copy(g_szQueueCallback[slot],   MAX_CALLBACK    - 1, callback);
    copy(g_szQueuePlugin[slot],     MAX_PLUGIN_NAME - 1, plugin_filename);
    copy(g_szQueueSessionId[slot],  MAX_SESSION_ID  - 1, session_id);

    return slot;
}

public native_cancel(plugin_id, num_params)
{
    new player = get_param(1);
    new session_id[MAX_SESSION_ID];
    if (num_params >= 2)
        get_string(2, session_id, MAX_SESSION_ID - 1);
    if (!session_id[0])
        num_to_str(player, session_id, MAX_SESSION_ID - 1);

    new slot = find_session_slot(session_id, player);
    if (slot != -1)
        free_slot(slot);
}

public native_is_pending(plugin_id, num_params)
{
    new player = get_param(1);
    new session_id[MAX_SESSION_ID];
    if (num_params >= 2)
        get_string(2, session_id, MAX_SESSION_ID - 1);
    if (!session_id[0])
        num_to_str(player, session_id, MAX_SESSION_ID - 1);

    return (find_session_slot(session_id, player) != -1) ? 1 : 0;
}

public native_set_plugin_context(plugin_id, num_params)
{
    new context[MAX_SYSTEM];
    get_string(1, context, MAX_SYSTEM - 1);

    new plugin_filename[MAX_PLUGIN_NAME];
    get_plugin(plugin_id, plugin_filename, MAX_PLUGIN_NAME - 1);

    TrieSetString(g_tSystemPrompts, plugin_filename, context);
}

public native_append_plugin_context(plugin_id, num_params)
{
    new plugin_filename[MAX_PLUGIN_NAME];
    get_plugin(plugin_id, plugin_filename, MAX_PLUGIN_NAME - 1);

    new existing[MAX_SYSTEM];
    TrieGetString(g_tSystemPrompts, plugin_filename, existing, MAX_SYSTEM - 1);

    new appended[MAX_SYSTEM];
    get_string(1, appended, MAX_SYSTEM - 1);

    new combined[MAX_SYSTEM];
    if (existing[0])
        format(combined, MAX_SYSTEM - 1, "%s^n%s", existing, appended);
    else
        copy(combined, MAX_SYSTEM - 1, appended);

    TrieSetString(g_tSystemPrompts, plugin_filename, combined);
}

public native_clear_memory(plugin_id, num_params)
{
    new player = get_param(1);
    new session_id[MAX_SESSION_ID];
    if (num_params >= 2)
        get_string(2, session_id, MAX_SESSION_ID - 1);
    if (!session_id[0])
        num_to_str(player, session_id, MAX_SESSION_ID - 1);

    new host[64];
    get_pcvar_string(g_pCvarHost, host, 63);
    new port = get_pcvar_num(g_pCvarPort);

    new err;
    new sock = socket_open(host, port, SOCKET_TCP, err);
    if (sock == -1 || err != 0)
        return;

    new escaped_session[MAX_SESSION_ID * 2];
    json_escape(session_id, escaped_session, sizeof(escaped_session) - 1);

    new request[MAX_SESSION_ID * 2 + 64];
    format(request, sizeof(request) - 1,
        "{^"type^":^"clear_memory^",^"player^":%d,^"session_id^":^"%s^"}^n",
        player, escaped_session);
    socket_send(sock, request, strlen(request));
    socket_close(sock);
}

public native_register_tool(plugin_id, num_params)
{
    if (g_iToolCount >= MAX_TOOLS) {
        log_amx("[GenAI] tool registry full");
        return;
    }

    new name[MAX_TOOL_NAME];
    new desc[MAX_TOOL_DESC];
    new callback[MAX_CALLBACK];
    get_string(1, name,     MAX_TOOL_NAME - 1);
    get_string(2, desc,     MAX_TOOL_DESC - 1);
    get_string(3, callback, MAX_CALLBACK  - 1);

    new plugin_filename[MAX_PLUGIN_NAME];
    get_plugin(plugin_id, plugin_filename, MAX_PLUGIN_NAME - 1);

    // Strip .amxx extension to get the prefix.
    new prefix[MAX_PLUGIN_NAME];
    copy(prefix, MAX_PLUGIN_NAME - 1, plugin_filename);
    new ext = strfind(prefix, ".amxx");
    if (ext != -1)
        prefix[ext] = 0;

    new t = g_iToolCount;
    format(g_szToolName[t], MAX_TOOL_NAME - 1, "%s__%s", prefix, name);
    copy(g_szToolDesc[t],     MAX_TOOL_DESC   - 1, desc);
    copy(g_szToolCallback[t], MAX_CALLBACK    - 1, callback);
    copy(g_szToolPlugin[t],   MAX_PLUGIN_NAME - 1, plugin_filename);
    copy(g_szToolParamsJson[t], MAX_TOOL_PARAMS_JSON - 1, "[]");
    g_iCurrentTool = t;
    g_iToolCount++;
}

public native_add_tool_param(plugin_id, num_params)
{
    if (g_iCurrentTool < 0) {
        log_amx("[GenAI] genai_add_tool_param called before genai_register_tool");
        return;
    }

    new pname[48];
    new ptype[16];
    new pdesc[128];
    get_string(1, pname,  sizeof(pname)  - 1);
    get_string(2, ptype,  sizeof(ptype)  - 1);
    new required = get_param(3);
    get_string(4, pdesc,  sizeof(pdesc)  - 1);

    new t = g_iCurrentTool;
    new cur_len = strlen(g_szToolParamsJson[t]);

    // Truncate the trailing ']'.
    g_szToolParamsJson[t][cur_len - 1] = 0;

    // Append comma separator after first param.
    if (cur_len > 2)  // more than just "["
        add(g_szToolParamsJson[t], MAX_TOOL_PARAMS_JSON - 1, ",");

    new escaped_name[96];
    new escaped_type[32];
    new escaped_desc[256];
    json_escape(pname, escaped_name, sizeof(escaped_name) - 1);
    json_escape(ptype, escaped_type, sizeof(escaped_type) - 1);
    json_escape(pdesc, escaped_desc, sizeof(escaped_desc) - 1);

    new entry[400];
    format(entry, sizeof(entry) - 1,
        "{^"name^":^"%s^",^"type^":^"%s^",^"required^":%s,^"description^":^"%s^"}",
        escaped_name, escaped_type,
        required ? "true" : "false",
        escaped_desc);
    add(g_szToolParamsJson[t], MAX_TOOL_PARAMS_JSON - 1, entry);
    add(g_szToolParamsJson[t], MAX_TOOL_PARAMS_JSON - 1, "]");
}

public native_register_skill(plugin_id, num_params)
{
    if (g_iSkillCount >= MAX_SKILLS) {
        log_amx("[GenAI] skill registry full");
        return;
    }

    new name[MAX_SKILL_NAME];
    get_string(1, name, MAX_SKILL_NAME - 1);

    new plugin_filename[MAX_PLUGIN_NAME];
    get_plugin(plugin_id, plugin_filename, MAX_PLUGIN_NAME - 1);

    new prefix[MAX_PLUGIN_NAME];
    copy(prefix, MAX_PLUGIN_NAME - 1, plugin_filename);
    new ext = strfind(prefix, ".amxx");
    if (ext != -1)
        prefix[ext] = 0;

    format(g_szSkillName[g_iSkillCount], MAX_SKILL_NAME - 1, "%s__%s", prefix, name);
    g_iSkillCount++;
}
