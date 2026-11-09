params ["_machine"];
(_machine get "LIST") select {
	alive (_x # 0) and {
		vehicle (_x # 0) isNotEqualTo (_machine get "VEHICLE")
	}
}
