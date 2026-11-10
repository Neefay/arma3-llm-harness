params ["_job"];
[_job get "SUBJECT"] call ace_medical_fnc_fullHeal;
[_job get "SUBJECT", _job get "GROUP"] call brmh_cmd_fnc_treated;
