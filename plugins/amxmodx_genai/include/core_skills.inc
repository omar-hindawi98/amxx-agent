#if defined _amxgenai_core_skills_included
    #endinput
#endif
#define _amxgenai_core_skills_included

stock register_core_skills()
{
    if (g_iSkillCount < MAX_SKILLS) {
        copy(g_szSkillName[g_iSkillCount], MAX_SKILL_NAME - 1, "amxmodx-reference");
        g_iSkillCount++;
    }
}
