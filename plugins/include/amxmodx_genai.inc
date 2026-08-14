#if defined _amxmodx_genai_included
    #endinput
#endif
#define _amxmodx_genai_included

#pragma reqlib amxmodx_genai
#if !defined AMXMODX_NOAUTOLOAD
    #pragma loadlib amxmodx_genai
#endif

// ---- Natives ----------------------------------------------------------------

/**
 * Sends a prompt scoped to this player's memory.
 *
 * The session key is the player's SteamID so memory survives reconnects and
 * map changes.
 *
 * Callback signature:
 *   public MyCallback(player, const response[], bool:is_error)
 *
 * is_error is true when the response is a sidecar error (timeout, unauthorized,
 * AI unavailable) rather than a real AI reply.
 *
 * @param player       Client index
 * @param prompt       User message to send
 * @param callback     Name of public function in calling plugin to receive response
 * @param this_plugin  Optional. When true, memory is isolated to this plugin only.
 *                     When false (default), memory is shared across all plugins for
 *                     the same player. Use true when your plugin has a distinct
 *                     persona that should not bleed into the player's shared history.
 * @param no_memory    Optional. When true the query runs with no history and the
 *                     response is not stored. Use for one-off lookups (stat queries,
 *                     admin commands) that should not pollute the session.
 * @return             Queue slot on success, -1 if queue is full or socket error
 */
native genai_query_player(player, const prompt[], const callback[], bool:this_plugin = false, bool:no_memory = false);

/**
 * Sends a prompt with an explicit session key. Use for custom scopes:
 *   - Team/group sessions:  "team_2", "ct_squad"
 *   - Server-wide session:  "server"
 *   - Any other shared context
 *
 * All callers that pass the same session_id share the same memory.
 *
 * Callback signature:
 *   public MyCallback(const response[], bool:is_error)
 *
 * is_error is true when the response is a sidecar error rather than a real AI reply.
 *
 * @param prompt       User message to send
 * @param callback     Name of public function in calling plugin to receive response
 * @param session_id   Conversation history key. Must be non-empty.
 * @param this_plugin  Optional. When true, session_id is prefixed with this plugin's
 *                     name so two plugins using "team_2" don't share the same memory.
 * @param no_memory    Optional. See genai_query_player.
 * @return             Queue slot on success, -1 if queue is full or socket error
 */
native genai_query(const prompt[], const callback[], const session_id[], bool:this_plugin = false, bool:no_memory = false);

/**
 * Cancels any pending query for this player / session. No callback is fired.
 *
 * @param player      Client index
 * @param session_id  Optional. Session to cancel. Defaults to player SteamID.
 */
native genai_cancel(player, const session_id[] = "");

/**
 * Returns true if a query is currently pending for this player / session.
 *
 * @param player      Client index
 * @param session_id  Optional. Session to check. Defaults to player SteamID.
 */
native bool:genai_is_pending(player, const session_id[] = "");

/**
 * Sets the plugin context section of the system prompt.
 * This text is appended to the immutable base system prompt under a
 * "## <plugin_name>" heading. It cannot override the base prompt.
 * Replaces any previously set plugin context. Call in plugin_init.
 *
 * Use genai_append_plugin_context to build the context incrementally.
 */
native genai_set_plugin_context(const context[]);

/**
 * Appends text to this plugin's system prompt section.
 * A newline is inserted between the existing content and the new text.
 * Headings in the appended text are automatically shifted down two levels
 * (# becomes ###, ## becomes ####, etc.) so they nest correctly under the
 * plugin's ## section heading.
 */
native genai_append_plugin_context(const content[]);

/**
 * Clears stored memory (conversation history) for a session.
 * Call on player disconnect or when starting a new context.
 *
 * @param player      Client index (for server-side reference)
 * @param session_id  Optional. Session to clear. Defaults to player SteamID.
 */
native genai_clear_memory(player, const session_id[] = "");

/**
 * Registers a skill available to the agent for all queries from the calling plugin.
 * Call in plugin_init. Skills are loaded from GENAI_SKILLS_PATH on the sidecar.
 *
 * The skill name is automatically prefixed with the plugin filename:
 * "strategy" in "my_plugin.amxx" becomes "my_plugin__strategy".
 * Place the skill directory at GENAI_SKILLS_PATH/my_plugin__strategy/SKILL.md
 * on the machine running the sidecar.
 *
 * @param name  Skill directory name (without the plugin prefix)
 */
native genai_register_skill(const name[]);

/**
 * Adds a typed parameter to the most recently registered tool.
 * Call immediately after genai_register_tool. Repeat for each parameter.
 *
 * Tools with declared parameters give Claude a strict schema to work with,
 * which improves argument accuracy over free-form JSON.
 *
 * @param name        Parameter name (snake_case)
 * @param type        JSON type: "string", "integer", "boolean", or "number"
 * @param required    True if Claude must always provide this argument
 * @param description One-sentence description Claude uses to fill the argument
 */
native genai_add_tool_param(const name[], const type[], bool:required, const description[]);

/**
 * Registers a tool Claude can call mid-reasoning. Claude sees the name and
 * description when deciding whether to use it. The callback is invoked
 * synchronously when Claude requests the tool.
 *
 * Callback signature:
 *   public MyTool(player, const args_json[], result[], maxlen)
 *     - args_json: flat JSON object of arguments Claude passed
 *     - result:    buffer to write the tool result string into
 *     - maxlen:    size of result buffer
 *     - return 1 on success
 *
 * Use json_get_string / json_get_int from amxmodx_genai/include/json.inc to
 * parse args_json.
 *
 * @param name        Tool name (snake_case, no spaces)
 * @param description One-sentence description visible to Claude
 * @param callback    Name of public function in calling plugin
 */
native genai_register_tool(const name[], const description[], const callback[]);

/**
 * Clears long-term (summary) memory for a session without touching short-term memory.
 * Use when you want to wipe a player's persistent AI memory completely, e.g. season reset.
 * Unlike genai_clear_memory, this does NOT trigger summarization - it discards the summary.
 *
 * @param player      Client index
 * @param session_id  Optional. Session to clear. Defaults to player SteamID.
 */
native genai_clear_longterm_memory(player, const session_id[] = "");
