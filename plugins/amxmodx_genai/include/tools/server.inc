#if defined _amxgenai_tools_server_included
    #endinput
#endif
#define _amxgenai_tools_server_included

stock register_server_tools()
{
    genai_register_tool(
        "change_map",
        "Changes the server to the specified map immediately.",
        "core_tool_change_map"
    );
    genai_add_tool_param("map", "string", true, "Map name to switch to (e.g. de_dust2)");

    genai_register_tool(
        "get_map_list",
        "Returns the list of maps from the server mapcycle.",
        "core_tool_get_map_list"
    );
}

public core_tool_change_map(player, const args_json[], result[], maxlen)
{
    new map[36];
    json_get_string(args_json, "map", map, sizeof(map) - 1);

    if (!map[0]) {
        copy(result, maxlen, "{^"error^":^"map name is empty^"}");
        return 1;
    }

    if (!is_map_valid(map)) {
        copy(result, maxlen, "{^"error^":^"map not found on server^"}");
        return 1;
    }

    server_cmd("changelevel %s", map);

    new esc_map[72];
    json_escape(map, esc_map, sizeof(esc_map) - 1);
    format(result, maxlen, "{^"ok^":true,^"map^":^"%s^"}", esc_map);
    return 1;
}

public core_tool_get_map_list(player, const args_json[], result[], maxlen)
{
    new mapcycle_file[128];
    get_cvar_string("mapcyclefile", mapcycle_file, sizeof(mapcycle_file) - 1);

    if (!mapcycle_file[0])
        copy(mapcycle_file, sizeof(mapcycle_file) - 1, "mapcycle.txt");

    new file = fopen(mapcycle_file, "r");
    if (!file) {
        copy(result, maxlen, "{^"error^":^"could not open mapcycle file^"}");
        return 1;
    }

    copy(result, maxlen, "[");
    new first = 1;
    new line[36];

    while (!feof(file)) {
        fgets(file, line, sizeof(line) - 1);
        trim(line);

        if (!line[0] || line[0] == ';' || line[0] == '/')
            continue;

        new esc_map[72];
        json_escape(line, esc_map, sizeof(esc_map) - 1);

        new entry[80];
        format(entry, sizeof(entry) - 1, "%s^"%s^"", first ? "" : ",", esc_map);
        add(result, maxlen, entry);
        first = 0;
    }

    fclose(file);
    add(result, maxlen, "]");
    return 1;
}
