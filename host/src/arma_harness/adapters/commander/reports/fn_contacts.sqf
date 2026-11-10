params ["_leader"];
private _near = _leader nearTargets 2000;
// A crewman is listed as a target of his own, with no type: whoever sees him sees the vehicle he's in, so it's the
// vehicle that's reported, once, known as well as he is if the vehicle itself isn't known yet.
private _seen = [];
{
	private _vehicle = vehicle _x;
	// A gun with nobody alive on it isn't a contact any more, though the engine keeps it on the list: the sightings
	// say it's been abandoned. As a contact it would seem manned again with every report.
	if ((_seen findIf {
		(_x # 0) isEqualTo _vehicle
	}) < 0 and {
		_vehicle isKindOf "CAManBase" or {
			({
				alive _x
			} count crew _vehicle) > 0
		}
	}) then {
		_seen pushBack [_vehicle, [_x, _vehicle] select ((_leader knowsAbout _vehicle) > 0)];
	};
} forEach ((_leader targets [true, 2000]) select {
	// A fire mission makes the engine put a hidden ArtilleryTarget at the aim point, on the other side. It isn't an
	// enemy to anyone, and once it's gone, what's known of it is a place at the map's origin.
	not isNull _x and {
		not ("ArtilleryTarget" in typeOf _x)
	}
});
// When each weapon or vehicle came into the leader's sight and stayed there: a steady look identifies it.
private _looks = (group _leader) getVariable ["brmh_cmd_looks", createHashMap];
(group _leader) setVariable ["brmh_cmd_looks", _looks];
_seen apply {
	_x params ["_object", "_known"];
	private _knowledge = _leader targetKnowledge _known;
	private _inSight = ([_leader, "VIEW", _object] checkVisibility [
		eyePos _leader,
		(getPosASL _object) vectorAdd [0, 0, 1]
	]) > 0.3;
	private _entry = _near findIf {
		(_x # 4) isEqualTo _object
	};
	private _type = switch (true) do {
		case (_entry >= 0): {
			(_near # _entry) # 1
		};
		case (_object isNotEqualTo _known): {
			typeOf _object
		};
		default {
			""
		};
	};
	// Position and type here are what the group believes. The true object must not leave this function, only the key
	// that the commander's list follows a weapon or vehicle by. Its model is said once the group knows it well.
	private _kind = [_type] call brmh_cmd_fnc_kind;
	private _materiel = not (_kind in ["unknown", "infantry"]);
	// Its model, once the leader knows it well (a fight does that fast) or has had a steady look within the range a
	// man with binoculars could tell: farther for a tank than for a gun on a tripod.
	private _since = if (_materiel and {
		_inSight
	}) then {
		_looks getOrDefault [hashValue _object, time]
	} else {
		-1
	};
	if (_since >= 0) then {
		_looks set [hashValue _object, _since];
	} else {
		_looks deleteAt (hashValue _object);
	};
	private _identifies = [400, 800] select (_kind in ["tank", "tracked vehicle", "APC", "helicopter", "aircraft", "boat"]);
	private _identified = _materiel and {
		(_leader knowsAbout _known) >= 2 or {
			_since >= 0 and {
				(time - _since) >= 20
			} and {
				(_leader distance _object) <= _identifies
			}
		}
	};
	createHashMapFromArray [
		["pos", [(_knowledge # 6) # 0, (_knowledge # 6) # 1]],
		["kind", _kind],
		["name", if (_identified) then {
			getText (configFile >> "CfgVehicles" >> _type >> "displayName")
		} else {
			""
		}],
		["key", if (_materiel) then {
			[_object] call brmh_cmd_fnc_targetKey
		} else {
			""
		}],
		// The engine stops renewing when a target that keeps still was last seen, so a gun in plain view went stale
		// within half a minute. In sight from the leader's eyes now, it's seen now.
		["age_s", if (_inSight) then {
			0
		} else {
			(time - (_knowledge # 2)) max 0
		}],
		["accuracy_m", if (_entry < 0) then {
			-1
		} else {
			(_near # _entry) # 5
		}]
	]
}
