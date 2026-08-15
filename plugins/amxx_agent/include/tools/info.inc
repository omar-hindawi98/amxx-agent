#if defined _amxagent_tools_info_included
    #endinput
#endif
#define _amxagent_tools_info_included

stock register_info_tools()
{
    agent_register_tool(
        "get_player_info",
        "Returns name, steamid, team, health, frags, and IP for a connected player.",
        "core_tool_get_player_info"
    );
    agent_add_tool_param("player_id", "integer", true, "Client index of the player to look up");

    agent_register_tool(
        "get_server_info",
        "Returns the current map, connected player count, max players, and server hostname.",
        "core_tool_get_server_info"
    );

    agent_register_tool(
        "get_players",
        "Returns all connected players with their index, name, steamid, and team.",
        "core_tool_get_players"
    );
}

public core_tool_get_player_info(player, const args_json[], result[], maxlen)
{
    new target = json_get_int(args_json, "player_id");

    if (!is_user_connected(target)) {
        copy(result, maxlen, "{^"error^":^"player not connected^"}");
        return 1;
    }

    new name[32], authid[36], ip[32];
    get_user_name(target, name, sizeof(name) - 1);
    get_user_authid(target, authid, sizeof(authid) - 1);
    get_user_ip(target, ip, sizeof(ip) - 1, 1);

    new team = get_user_team(target);
    new health = get_user_health(target);
    new frags = get_user_frags(target);

    new esc_name[64], esc_authid[72], esc_ip[64];
    json_escape(name,   esc_name,   sizeof(esc_name)   - 1);
    json_escape(authid, esc_authid, sizeof(esc_authid) - 1);
    json_escape(ip,     esc_ip,     sizeof(esc_ip)     - 1);

    new team_str[12];
    if      (team == 1) copy(team_str, sizeof(team_str) - 1, "T");
    else if (team == 2) copy(team_str, sizeof(team_str) - 1, "CT");
    else if (team == 3) copy(team_str, sizeof(team_str) - 1, "spectator");
    else                copy(team_str, sizeof(team_str) - 1, "unassigned");

    format(result, maxlen,
        "{^"player_id^":%d,^"name^":^"%s^",^"steamid^":^"%s^",^"team^":^"%s^",^"health^":%d,^"frags^":%d,^"ip^":^"%s^"}",
        target, esc_name, esc_authid, team_str, health, frags, esc_ip);
    return 1;
}

public core_tool_get_server_info(player, const args_json[], result[], maxlen)
{
    new map[36], hostname[64];
    get_mapname(map, sizeof(map) - 1);
    get_cvar_string("hostname", hostname, sizeof(hostname) - 1);

    new esc_map[72], esc_hostname[128];
    json_escape(map,      esc_map,      sizeof(esc_map)      - 1);
    json_escape(hostname, esc_hostname, sizeof(esc_hostname) - 1);

    format(result, maxlen,
        "{^"map^":^"%s^",^"players^":%d,^"max_players^":%d,^"hostname^":^"%s^"}",
        esc_map, get_playersnum(), get_maxplayers(), esc_hostname);
    return 1;
}

public core_tool_get_players(player, const args_json[], result[], maxlen)
{
    copy(result, maxlen, "[");
    new first = 1;

    for (new id = 1; id <= get_maxplayers(); id++) {
        if (!is_user_connected(id))
            continue;

        new name[32], authid[36];
        get_user_name(id, name, sizeof(name) - 1);
        get_user_authid(id, authid, sizeof(authid) - 1);

        new team = get_user_team(id);
        new team_str[12];
        if      (team == 1) copy(team_str, sizeof(team_str) - 1, "T");
        else if (team == 2) copy(team_str, sizeof(team_str) - 1, "CT");
        else if (team == 3) copy(team_str, sizeof(team_str) - 1, "spectator");
        else                copy(team_str, sizeof(team_str) - 1, "unassigned");

        new esc_name[64], esc_authid[72];
        json_escape(name,   esc_name,   sizeof(esc_name)   - 1);
        json_escape(authid, esc_authid, sizeof(esc_authid) - 1);

        new entry[200];
        format(entry, sizeof(entry) - 1,
            "%s{^"player_id^":%d,^"name^":^"%s^",^"steamid^":^"%s^",^"team^":^"%s^"}",
            first ? "" : ",", id, esc_name, esc_authid, team_str);
        add(result, maxlen, entry);
        first = 0;
    }

    add(result, maxlen, "]");
    return 1;
}
