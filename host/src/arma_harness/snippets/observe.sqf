/*
	Observers for conversational use (comments are stripped by the host). Run on "all"; re-running replaces the handlers.
	- Interface machines: typed chat -> "evt" type "chat" {channel, from, text}, reported by the sender's
	  machine only. HandleChatMessage does not
	  fire for script chat commands (systemChat, sideChat...), so replies never loop back.
	- Server: deaths -> "evt" type "killed" {victim, side, killer, killerSide, weapon, distance}.
	Event handler code must not use chat commands (the wiki warns of recursion freezes).
*/
if (hasInterface) then {
	if (not isNil "brmh_observeChatEh") then {
		removeMissionEventHandler ["HandleChatMessage", brmh_observeChatEh];
	};
	brmh_observeChatEh = addMissionEventHandler ["HandleChatMessage", {
		params ["_channel", "_owner", "_from", "_text", "_person", "_name", "_strID", "_forcedDisplay", "_isPlayerMessage", "_sentenceType"];
		// Every machine sees the message; only the sender's own reports it, so it arrives once. AI radio
		// lines have the AI unit as _person. Typed chat arrives with sentenceType 1 (observed in 2.22,
		// despite the wiki calling 1 "protocol"), so the type is not used as a filter. Lines that
		// say.sqf posts (customChat does fire this handler) are skipped through brmh_saying.
		if (_person isEqualTo player and {
			isNil "brmh_saying"
		}) then {
			["evt", createHashMapFromArray [
				["type", "chat"],
				["channel", _channel],
				["from", _from],
				["name", _name],
				["text", _text]
			]] call BRMH_fnc_emit;
		};
		false
	}];
};

if (isServer) then {
	if (not isNil "brmh_observeKilledEh") then {
		removeMissionEventHandler ["EntityKilled", brmh_observeKilledEh];
	};
	brmh_observeKilledEh = addMissionEventHandler ["EntityKilled", {
		params ["_victim", "_killer", "_instigator"];
		private _by = if (isNull _instigator) then {
			_killer
		} else {
			_instigator
		};
		// A unit killed by script, a fall or a collision is reported as its own killer.
		if (_by isEqualTo _victim) then {
			_by = objNull;
		};
		["evt", createHashMapFromArray [
			["type", "killed"],
			["victim", if (_victim isKindOf "CAManBase") then {
				name _victim
			} else {
				getText (configOf _victim >> "displayName")
			}],
			["victimType", typeOf _victim],
			["victimIsPlayer", isPlayer _victim],
			["victimPos", (getPosATL _victim) apply {
				round _x
			}],
			["side", str side group _victim],
			["killerIsPlayer", not isNull _by and {
				isPlayer _by
			}],
			["killer", if (isNull _by) then {
				""
			} else {
				name _by
			}],
			["killerSide", if (isNull _by) then {
				""
			} else {
				str side group _by
			}],
			["weapon", if (isNull _by) then {
				""
			} else {
				currentWeapon _by
			}],
			["distance", if (isNull _by) then {
				-1
			} else {
				round (_by distance _victim)
			}]
		]] call BRMH_fnc_emit;
	}];
};
[hasInterface, isServer]
