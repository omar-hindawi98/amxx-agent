#if defined _amxagent_tools_comm_incl #endinput #endif #define
_amxagent_tools_comm_incl stock register_communication_tools() {
agent_register_tool( "say", "Broadcasts a chat message to all players as the
server.", "core_tool_say" ); agent_add_tool_param("message", "string", true,
"Message text to broadcast"); agent_register_tool( "say_to_player", "Sends a
private chat message to a single connected player.", "core_tool_say_to_player"
); agent_add_tool_param("player_id", "integer", true, "Client index of the
target player"); agent_add_tool_param("message", "string", true, "Message text
to send"); } public core_tool_say(player, const args_json[], result[], maxlen) {
new message[192]; json_get_string(args_json, "message", message, sizeof(message)
- 1); if (!message[0]) { copy(result, maxlen, "{^"error^":^"message is
empty^"}"); return 1; } client_print(0, print_chat, "%s", message); copy(result,
maxlen, "{^"ok^":true}"); return 1; } public core_tool_say_to_player(player,
const args_json[], result[], maxlen) { new target = json_get_int(args_json,
"player_id"); if (!is_user_connected(target)) { copy(result, maxlen,
"{^"error^":^"player not connected^"}"); return 1; } new message[192];
json_get_string(args_json, "message", message, sizeof(message) - 1); if
(!message[0]) { copy(result, maxlen, "{^"error^":^"message is empty^"}"); return
1; } client_print(target, print_chat, "%s", message); copy(result, maxlen,
"{^"ok^":true}"); return 1; }
