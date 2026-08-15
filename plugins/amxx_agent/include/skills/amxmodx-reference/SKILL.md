---
name: amxmodx-reference
description: Reference knowledge about AMX Mod X - what it is, how plugins work, Pawn scripting, server administration, and common gameplay systems. Use when asked to explain AMX Mod X concepts, help with plugin logic, or answer questions about server administration.
---
# AMX Mod X Reference

You are an expert on AMX Mod X (AMXMODX). When invoked, answer the specific question using the knowledge below. Be concise.

## What is AMX Mod X?

AMX Mod X is a Metamod plugin for Half-Life engine games (GoldSrc engine). It allows server administrators to write server-side plugins in Pawn to extend or modify game logic. Most commonly used with Counter-Strike 1.6 and other GoldSrc titles.

Key facts:
- Runs on top of Metamod, which sits between the Half-Life engine (hlds) and game mods.
- Plugins are compiled Pawn scripts (.amxx files) loaded by the server at startup or via `amx_plugins`.
- Plugins can hook game events, register console commands, manipulate players, manage teams, and call back into the engine.

## Plugin System

Plugins register with `register_plugin(name, version, author)` in `plugin_init()`.

Lifecycle callbacks:
- `plugin_init()` - called once on load; register cvars, commands, forwards, natives.
- `plugin_end()` - cleanup on unload.
- `plugin_cfg()` - called after `server.cfg`; safe for reading cvars.
- `plugin_precache()` - precache models/sounds before map load.
- `client_connect(id)` / `client_disconnect(id)` - player connect/disconnect.

## Pawn Language Basics

Pawn is a C-like scripting language with no pointers and fixed-size arrays.

- Variables: `new x = 5;` - all variables are integers unless tagged.
- Strings: fixed-length char arrays, e.g. `new name[32]`.
- `public` functions are callable as forwards/callbacks; `stock` functions are inlined or dropped if unused.
- No dynamic memory allocation. Array sizes must be compile-time constants.
- String functions: `format()`, `copy()`, `add()`, `strfind()`, `strcmp()`, `strlen()`.
- Type tags: `Float:`, `bool:`, `Trie:`, `Array:`.

## Players

Players are identified by a client index (1 to `MaxClients`, typically 32). Index 0 is the server console.

Common natives:
- `get_players(players, count, flags, team)` - get array of connected players.
- `get_user_name(id, name, len)` - player name.
- `get_user_authid(id, auth, len)` - SteamID string (e.g. `STEAM_0:1:12345`) or `BOT`/`HLTV`.
- `get_user_team(id)` - 1 = T, 2 = CT, 0 = spectator/unassigned.
- `get_user_health(id)` / `get_user_armor(id)`.
- `is_user_alive(id)` / `is_user_connected(id)` / `is_user_admin(id)`.
- `client_print(id, type, msg, ...)` - send message; type 1 = console, 2 = chat.
- `client_cmd(id, cmd)` - execute command on the client.
- `server_cmd(cmd)` - execute command on the server.
- `kick(id, reason)` / `ban(id, time, type, reason)`.

## CVars

- `register_cvar(name, default)` - returns a cvar handle.
- `get_pcvar_num(h)` / `get_pcvar_float(h)` / `get_pcvar_string(h, buf, len)`.
- `set_pcvar_num(h, value)` / `set_pcvar_string(h, value)`.

## Events and Forwards

- `register_event(event, callback, flags)` - hook a game event (e.g. `"DeathMsg"`, `"RoundEnd"`).
- `register_logevent(callback, num_args, ...)` - hook a log event string.
- `register_forward(forward_id, callback)` - hook an engine/metamod forward.
- `set_task(delay, callback, id, param, len, flags)` - schedule a callback.
- `remove_task(id)` - cancel a scheduled task.

## Console Commands and Menus

- `register_concmd(cmd, callback, access, info)` - server console command.
- `register_clcmd(cmd, callback, access, info)` - client command.
- `register_saycmd(cmd, callback, access)` - hook a chat `say` command (e.g. `/help`).

Menus: `menu_create`, `menu_additem`, `menu_display`, callback receives item index.

## Data Structures

- `TrieCreate()` / `TrieSetCell()` / `TrieGetCell()` / `TrieSetString()` / `TrieGetString()` / `TrieDestroy()`.
- `ArrayCreate()` / `ArrayPushCell()` / `ArrayGetCell()` / `ArrayDestroy()`.

## Admin System

Access flags are bit flags: `ADMIN_KICK`, `ADMIN_BAN`, `ADMIN_SLAY`, `ADMIN_IMMUNITY`, etc.
- `get_user_flags(id)` - returns combined flag bits for the player.
- `access(id, flags)` - true if the player has all specified flags.
- Accounts defined in `addons/amxmodx/configs/users.ini`.

## Common Plugin Patterns

Rate-limiting a player command:
```pawn
new Float:g_fLastCmd[33];
public cmd_something(id) {
    if (get_gametime() - g_fLastCmd[id] < 3.0) {
        client_print(id, print_chat, "Wait before using this again.");
        return PLUGIN_HANDLED;
    }
    g_fLastCmd[id] = get_gametime();
    // ...
    return PLUGIN_HANDLED;
}
```

Iterating over alive players:
```pawn
new players[32], count;
get_players(players, count, "a"); // "a" = alive only
for (new i = 0; i < count; i++) {
    new id = players[i];
    // ...
}
```

## File Structure

```
addons/amxmodx/
  configs/    - amxx.cfg, users.ini, maps.ini
  plugins/    - compiled .amxx plugin files
  scripting/  - .sma source files and the compiler (amxxpc)
  logs/       - plugin and error logs
  data/       - plugin data files
  modules/    - native extension modules (.so/.dll)
```
