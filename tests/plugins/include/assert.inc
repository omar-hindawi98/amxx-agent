#if defined _amxtest_assert_included
    #endinput
#endif
#define _amxtest_assert_included

// Writes to server console (captured by docker logs).
// Format: [AMXTEST] <PASS|FAIL> [suite] label ...

new g_iTestPassed;
new g_iTestFailed;
new g_szSuite[64];

stock test_suite(const name[])
{
    copy(g_szSuite, sizeof(g_szSuite) - 1, name);
}

stock assert_str_eq(const actual[], const expected[], const label[])
{
    if (equal(actual, expected)) {
        g_iTestPassed++;
        server_print("[AMXTEST] PASS [%s] %s", g_szSuite, label);
    } else {
        g_iTestFailed++;
        server_print("[AMXTEST] FAIL [%s] %s | expected ^"%s^" got ^"%s^"",
            g_szSuite, label, expected, actual);
    }
}

stock assert_int_eq(actual, expected, const label[])
{
    if (actual == expected) {
        g_iTestPassed++;
        server_print("[AMXTEST] PASS [%s] %s", g_szSuite, label);
    } else {
        g_iTestFailed++;
        server_print("[AMXTEST] FAIL [%s] %s | expected %d got %d",
            g_szSuite, label, expected, actual);
    }
}

stock assert_true(bool:condition, const label[])
{
    if (condition) {
        g_iTestPassed++;
        server_print("[AMXTEST] PASS [%s] %s", g_szSuite, label);
    } else {
        g_iTestFailed++;
        server_print("[AMXTEST] FAIL [%s] %s | expected true", g_szSuite, label);
    }
}

stock test_results()
{
    server_print("[AMXTEST RESULTS] passed=%d failed=%d", g_iTestPassed, g_iTestFailed);
}
