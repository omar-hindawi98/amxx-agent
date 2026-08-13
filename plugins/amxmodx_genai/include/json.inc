// Minimal flat-JSON helpers. Requires constants.inc.

#if defined _amxgenai_json_included
    #endinput
#endif
#define _amxgenai_json_included

stock json_escape(const src[], dst[], max_dst)
{
    new j = 0;
    new len = strlen(src);
    for (new i = 0; i < len && j < max_dst - 2; i++) {
        new c = src[i];
        if (c == 34 || c == '\\') {
            dst[j++] = '\\';
        } else if (c == 10) {
            dst[j++] = '\\';
            dst[j++] = 'n';
            continue;
        } else if (c == 13) {
            continue;
        }
        dst[j++] = c;
    }
    dst[j] = 0;
}

// Returns 1 on success, 0 if key not found.
stock json_get_string(const json[], const key[], out[], maxlen)
{
    new pattern[MAX_TOOL_NAME + 4];
    format(pattern, sizeof(pattern) - 1, "\"%s\":\"", key);

    new pos = strfind(json, pattern);
    if (pos == -1)
        return 0;

    pos += strlen(pattern);
    new j = 0;
    new len = strlen(json);
    while (pos < len && j < maxlen - 1) {
        new c = json[pos];
        if (c == 34)
            break;
        if (c == '\\' && pos + 1 < len) {
            pos++;
            c = json[pos];
            if (c == 'n')               { out[j++] = 10; pos++; continue; }
            else if (c == 'r')          { out[j++] = 13; pos++; continue; }
            else if (c == 34 || c == '\\') { out[j++] = c;  pos++; continue; }
        }
        out[j++] = c;
        pos++;
    }
    out[j] = 0;
    return 1;
}

// Returns 0 if key not found.
stock json_get_int(const json[], const key[])
{
    new pattern[MAX_TOOL_NAME + 3];
    format(pattern, sizeof(pattern) - 1, "\"%s\":", key);

    new pos = strfind(json, pattern);
    if (pos == -1)
        return 0;

    pos += strlen(pattern);
    new len = strlen(json);
    while (pos < len && (json[pos] == ' ' || json[pos] == 9))
        pos++;
    if (pos >= len)
        return 0;

    new buf[16];
    new j = 0;
    while (pos < len && j < 15) {
        new c = json[pos];
        if (c < '0' || c > '9')
            break;
        buf[j++] = c;
        pos++;
    }
    buf[j] = 0;
    return str_to_num(buf);
}
