#if defined _amxgenai_tools_moderation_included
    #endinput
#endif
#define _amxgenai_tools_moderation_included

stock register_moderation_tools()
{
    genai_register_tool(
        "kick_player",
        "Kicks a connected player from the server with an optional reason.",
        "core_tool_kick_player"
    );
    genai_add_tool_param("player_id", "integer", true,  "Client index of the player to kick");
    genai_add_tool_param("reason",    "string",  false, "Reason shown to the player");

    genai_register_tool(
        "ban_player",
        "Bans a connected player. Use minutes=0 for a permanent ban.",
        "core_tool_ban_player"
    );
    genai_add_tool_param("player_id", "integer", true,  "Client index of the player to ban");
    genai_add_tool_param("minutes",   "integer", true,  "Ban duration in minutes; 0 = permanent");
    genai_add_tool_param("reason",    "string",  false, "Reason for the ban");

    genai_register_tool(
        "slap_player",
        "Slaps a connected player, dealing the specified damage and knocking them back.",
        "core_tool_slap_player"
    );
    genai_add_tool_param("player_id", "integer", true,  "Client index of the player to slap");
    genai_add_tool_param("damage",    "integer", false, "Damage to deal (default 0)");
}

public core_tool_kick_player(player, const args_json[], result[], maxlen)
{
    new target = json_get_int(args_json, "player_id");

    if (!is_user_connected(target)) {
        copy(result, maxlen, "{^"error^":^"player not connected^"}");
        return 1;
    }

    new reason[128];
    json_get_string(args_json, "reason", reason, sizeof(reason) - 1);

    if (reason[0])
        server_cmd("kick #%d ^"%s^"", get_user_userid(target), reason);
    else
        server_cmd("kick #%d", get_user_userid(target));

    copy(result, maxlen, "{^"ok^":true}");
    return 1;
}

public core_tool_ban_player(player, const args_json[], result[], maxlen)
{
    new target = json_get_int(args_json, "player_id");

    if (!is_user_connected(target)) {
        copy(result, maxlen, "{^"error^":^"player not connected^"}");
        return 1;
    }

    new minutes = json_get_int(args_json, "minutes");

    new reason[128];
    json_get_string(args_json, "reason", reason, sizeof(reason) - 1);

    new authid[36];
    get_user_authid(target, authid, sizeof(authid) - 1);

    server_cmd("banid %d %s kick; writeid", minutes, authid);

    if (reason[0]) {
        new esc_reason[256];
        json_escape(reason, esc_reason, sizeof(esc_reason) - 1);
        format(result, maxlen, "{^"ok^":true,^"steamid^":^"%s^",^"minutes^":%d,^"reason^":^"%s^"}", authid, minutes, esc_reason);
    } else {
        format(result, maxlen, "{^"ok^":true,^"steamid^":^"%s^",^"minutes^":%d}", authid, minutes);
    }
    return 1;
}

public core_tool_slap_player(player, const args_json[], result[], maxlen)
{
    new target = json_get_int(args_json, "player_id");

    if (!is_user_connected(target)) {
        copy(result, maxlen, "{^"error^":^"player not connected^"}");
        return 1;
    }

    if (!is_user_alive(target)) {
        copy(result, maxlen, "{^"error^":^"player is not alive^"}");
        return 1;
    }

    new damage = json_get_int(args_json, "damage");
    user_slap(target, damage);

    format(result, maxlen, "{^"ok^":true,^"damage^":%d}", damage);
    return 1;
}
