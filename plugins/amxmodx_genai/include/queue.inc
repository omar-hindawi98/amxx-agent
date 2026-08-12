// Queue state, registries, and slot helpers. Requires constants.inc.

#if defined _amxgenai_queue_included
    #endinput
#endif
#define _amxgenai_queue_included

// ---- queue state ------------------------------------------------------------

new g_iQueuePlayer[MAX_QUEUE];                   // client index for callback routing
new g_szQueueSessionId[MAX_QUEUE][MAX_SESSION_ID]; // history key
new g_szQueueCallback[MAX_QUEUE][MAX_CALLBACK];
new g_szQueuePlugin[MAX_QUEUE][MAX_PLUGIN_NAME];
new g_iQueueSocket[MAX_QUEUE];
new g_szQueueBuf[MAX_QUEUE][MAX_RESPONSE];
new g_iQueueBufLen[MAX_QUEUE];
new g_szQueueResponse[MAX_QUEUE][MAX_RESPONSE];
new bool:g_bQueueUsed[MAX_QUEUE];

// ---- tool registry ----------------------------------------------------------

new g_szToolName[MAX_TOOLS][MAX_TOOL_NAME];          // prefixed: plugin__name
new g_szToolDesc[MAX_TOOLS][MAX_TOOL_DESC];
new g_szToolParamsJson[MAX_TOOLS][MAX_TOOL_PARAMS_JSON]; // JSON array of param objects
new g_szToolCallback[MAX_TOOLS][MAX_CALLBACK];
new g_szToolPlugin[MAX_TOOLS][MAX_PLUGIN_NAME];
new g_iToolCount;
new g_iCurrentTool = -1;                             // target for genai_add_tool_param

// ---- skill registry ---------------------------------------------------------

new g_szSkillName[MAX_SKILLS][MAX_SKILL_NAME];   // prefixed: plugin__name
new g_iSkillCount;

// ---- per-plugin system prompts ----------------------------------------------
new Trie:g_tSystemPrompts;

// ---- slot helpers -----------------------------------------------------------

stock find_free_slot()
{
    for (new i = 0; i < MAX_QUEUE; i++)
        if (!g_bQueueUsed[i])
            return i;
    return -1;
}

// Find an active slot by session_id. Falls back to player if no session.
stock find_session_slot(const session_id[], player)
{
    for (new i = 0; i < MAX_QUEUE; i++) {
        if (!g_bQueueUsed[i])
            continue;
        if (equal(g_szQueueSessionId[i], session_id))
            return i;
    }
    // fallback: match by player index (handles pre-session-id callers)
    for (new i = 0; i < MAX_QUEUE; i++) {
        if (g_bQueueUsed[i] && g_iQueuePlayer[i] == player)
            return i;
    }
    return -1;
}

stock free_slot(slot)
{
    if (g_iQueueSocket[slot] != -1)
        socket_close(g_iQueueSocket[slot]);
    g_bQueueUsed[slot]              = false;
    g_iQueueSocket[slot]            = -1;
    g_iQueueBufLen[slot]            = 0;
    g_szQueueBuf[slot][0]           = 0;
    g_szQueueResponse[slot][0]      = 0;
    g_szQueueSessionId[slot][0]     = 0;
}

stock socket_send_str(sock, const msg[])
{
    return socket_send(sock, msg, strlen(msg));
}
