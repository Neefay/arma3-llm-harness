params ["_machine"];
((_machine get "VEHICLE") getVariable ["brmh_cmd_shots", 0]) - (_machine get "SHOTS")
