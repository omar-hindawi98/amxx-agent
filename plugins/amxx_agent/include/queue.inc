// Queue state, registries, and slot helpers. Requires constants.inc. #if
defined _amxagent_queue_included #endinput #endif #define
_amxagent_queue_included // ---- queue state
------------------------------------------------------------ new
g_iQueuePlayer[MAX_QUEUE]; // client index for callback routing new
g_szQueueSessionId[MAX_QUEUE][MAX_SESSION_ID]; // history key new
g_szQueueRequestId[MAX_QUEUE][MAX_REQUEST_ID]; // multiplexing key for the
persistent socket new g_szQueueCallback[MAX_QUEUE][MAX_CALLBACK]; new
g_szQueuePlugin[MAX_QUEUE][MAX_PLUGIN_NAME]; new
g_szQueueResponse[MAX_QUEUE][MAX_RESPONSE]; new bool:g_bQueueUsed[MAX_QUEUE];
new bool:g_bQueueError[MAX_QUEUE]; // true when the sidecar sent status="error"
for this slot new bool:g_bQueueNoPlayer[MAX_QUEUE]; // true for agent_query:
callback is (response[]) not (player, response[]) // ---- persistent connection
state -------------------------------------------- new g_iMainSocket = -1; //
single shared TCP socket to the sidecar new g_iRequestCounter = 0; //
incremented per query to generate unique request_ids new bool:g_bPolling =
false; new g_szMainBuf[MAX_RESPONSE * 2]; // global line-assembly buffer new
g_iMainBufLen = 0; // ---- tool registry
---------------------------------------------------------- new
g_szToolName[MAX_TOOLS][MAX_TOOL_NAME]; // prefixed: plugin__name new
g_szToolDesc[MAX_TOOLS][MAX_TOOL_DESC]; new
g_szToolParamsJson[MAX_TOOLS][MAX_TOOL_PARAMS_JSON]; // JSON array of param
objects new g_szToolCallback[MAX_TOOLS][MAX_CALLBACK]; new
g_szToolPlugin[MAX_TOOLS][MAX_PLUGIN_NAME]; new g_iToolCount; new g_iCurrentTool
= -1; // target for agent_add_tool_param // ---- skill registry
--------------------------------------------------------- new
g_szSkillName[MAX_SKILLS][MAX_SKILL_NAME]; // prefixed: plugin__name new
g_iSkillCount; // ---- per-plugin system prompts
---------------------------------------------- new Trie:g_tSystemPrompts; //
---- slot helpers -----------------------------------------------------------
stock find_free_slot() { for (new i = 0; i < MAX_QUEUE; i++) if
(!g_bQueueUsed[i]) return i; return -1; } // Find an active slot by session_id.
Falls back to player if no session. stock find_session_slot(const session_id[],
player) { for (new i = 0; i < MAX_QUEUE; i++) { if (!g_bQueueUsed[i]) continue;
if (equal(g_szQueueSessionId[i], session_id)) return i; } // fallback: match by
player index (handles pre-session-id callers) for (new i = 0; i < MAX_QUEUE;
i++) { if (g_bQueueUsed[i] && g_iQueuePlayer[i] == player) return i; } return
-1; } stock find_slot_by_request_id(const request_id[]) { for (new i = 0; i <
MAX_QUEUE; i++) if (g_bQueueUsed[i] && equal(g_szQueueRequestId[i], request_id))
return i; return -1; } stock free_slot(slot) { g_bQueueUsed[slot] = false;
g_bQueueError[slot] = false; g_bQueueNoPlayer[slot] = false;
g_szQueueResponse[slot][0] = 0; g_szQueueSessionId[slot][0] = 0;
g_szQueueRequestId[slot][0] = 0; } stock socket_send_str(sock, const msg[]) {
return socket_send(sock, msg, strlen(msg)); }
