// Whether a man is on the squad's side. By his group's side: ACE can make a man who's down captive, which changes his own.
// The enemy's downed are never carried, treated or listed.
params ["_group", "_man"];
((side _group) getFriend (side group _man)) >= 0.6
