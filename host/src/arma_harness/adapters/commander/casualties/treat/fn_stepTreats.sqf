// Each step: casualties waiting on a TREAT order go to the squad's free medics, one each. The medics' jobs are
// brmh_cmd_treatMachine, stepped with the other machines.
{
	private _treat = _x;
	private _group = _treat get "group";
	private _order = _treat get "order";
	private _queue = _treat get "queue";
	private _free = (units _group) select {
		[_x] call brmh_cmd_fnc_able and {
			[_x] call brmh_cmd_fnc_isMedic
		} and {
			not (_x getVariable ["brmh_cmd_busy", false])
		}
	};
	// Nobody's left waiting without a word: the commander, or a chained order, is relying on hearing how each ends.
	_queue = _queue select {
		private _still = alive _x and {
			not ([_x] call brmh_cmd_fnc_able)
		};
		if (not _still) then {
			[_group, _order, "treat", _x, ["he died", "up"] select (alive _x)] call brmh_cmd_fnc_careSay;
		};
		_still
	};
	if (_queue isNotEqualTo [] and {
		((units _group) findIf {
			[_x] call brmh_cmd_fnc_able and {
				[_x] call brmh_cmd_fnc_isMedic
			}
		}) < 0
	}) then {
		{
			[_group, _order, "treat", _x, "no medic"] call brmh_cmd_fnc_careSay;
		} forEach _queue;
		_queue = [];
	};
	// On an ordinary vehicle, or on somebody's shoulder: either way, not yet.
	private _waiting = _queue select {
		(vehicle _x isNotEqualTo _x and {
			not ([vehicle _x] call brmh_cmd_fnc_isMedicalVehicle)
		}) or {
			(_x getVariable ["brmh_cmd_handled", ""]) in ["carried", "treated"]
		}
	};
	_queue = _queue - _waiting;
	while {
		_free isNotEqualTo [] and {
			_queue isNotEqualTo []
		}
	} do {
		private _medic = _free deleteAt 0;
		private _man = _queue deleteAt 0;
		_medic setVariable ["brmh_cmd_busy", true];
		_medic enableAI "PATH";
		_man setVariable ["brmh_cmd_handled", "treated"];
		if (vehicle _medic isNotEqualTo _medic) then {
			[_medic] call brmh_cmd_fnc_getOff;
		};
		private _job = [brmh_cmd_treatMachine, [["GROUP", _group], ["ORDER", _order], ["SUBJECT", _man], ["MEDIC", _medic], ["TREAT", _treat], ["TRIES", 0], ["LAST", getPosATL _medic], ["MOVED", time], ["ORDERED", time], ["NEED", 0], ["STABLE", false], ["ANIM", time]]] call brmh_cmd_fnc_newMachine;
		[_job] call brmh_cmd_fnc_treatApproach;
		brmh_cmd_builds pushBack _job;
		[_group, _order, "treat", _man, "going"] call brmh_cmd_fnc_careSay;
	};
	_treat set ["queue", _queue + _waiting];
} forEach brmh_cmd_treats;
// An order is done when nobody's waiting on it and none of its medics is still at work.
brmh_cmd_treats = brmh_cmd_treats select {
	private _treat = _x;
	(_treat get "queue") isNotEqualTo [] or {
		(brmh_cmd_builds findIf {
			((_x get "SPEC") get "KIND") isEqualTo "treat" and {
				(_x get "STATE") isNotEqualTo ""
			} and {
				((_x get "TREAT") get "order") isEqualTo (_treat get "order")
			} and {
				(_x get "GROUP") isEqualTo (_treat get "group")
			}
		}) >= 0
	}
};
