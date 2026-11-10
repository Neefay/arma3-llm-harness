// Only matters when ACE is loaded. ACE's AI medic gives a medic orders of its own every 10 s, whenever a casualty in his group
// asks, and a medic sent to carry someone then stood still for good in about 1 run in 4. So treatment is by the commander's
// orders instead. See docs/COMMANDER_CASEVAC.md.
force ace_medical_ai_enabledFor = 0;
