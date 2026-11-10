// Free seats of a kind, in the game's own order. A seat with a dead man in it counts as free. The engine lets someone take it.
params ["_vehicle", "_kind"];
(fullCrew [_vehicle, "", true]) select {
	(_x # 1) isEqualTo _kind and {
		isNull (_x # 0) or {
			not alive (_x # 0)
		}
	}
}
