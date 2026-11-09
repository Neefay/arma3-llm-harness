params ["_rows"];
(_rows apply {
	brmh_cmd_men getOrDefault [_x # 0, objNull]
}) select {
	not isNull _x
}
