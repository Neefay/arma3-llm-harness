// Nothing left to drop or shoot. Flares and the designator's batteries aren't weapons.
params ["_vehicle"];
((magazinesAllTurrets _vehicle) findIf {
	(_x # 2) > 0 and {
		not ("cmflare" in toLowerANSI (_x # 0))
	} and {
		(_x # 0) isNotEqualTo "Laserbatteries"
	}
}) < 0
