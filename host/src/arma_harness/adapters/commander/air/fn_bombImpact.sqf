/*
	NAME: brmh_cmd_fnc_bombImpact
	DESCRIPTION: Where an unguided bomb released now would land. The engine flies a bomb as a missile: it has an axis,
		starting along the aircraft's velocity and turning toward its own; drag acts along the axis, and its side
		friction (the ammo's maneuvrability) damps any velocity across it, which holds the fall back like lift. Fitted
		to the Mk82's flight (host/tests/spikes/cas/spike_bomb_drag.py): within 25 m of the real throw of 1.8-1.9 km.
		Drag alone was 300 m short. The drag and turn rate are BRMH_CMD_BOMB_DRAG and BRMH_CMD_BOMB_TURN (init.sqf),
		stepped every 0.1 s for at most 60 s of fall.
	PARAMETERS:
		0 - Release position, ASL (ARRAY)
		1 - Release velocity, the aircraft's, m/s (ARRAY)
		2 - Side friction: the ammo's maneuvrability, as brmh_cmd_fnc_bombWeapon gives it (NUMBER)
	USAGE:
		private _impact = [getPosASL _vehicle, velocity _vehicle, _machine get "SIDE"] call brmh_cmd_fnc_bombImpact;
	RETURNS: Where it meets the ground, ASL (ARRAY). Where it is after 60 s if it hasn't yet.
	ENVIRONMENT: Any, unscheduled. Run every frame on an unguided strike's run.
*/
params ["_position", "_velocity", "_side"];
private _step = 0.1;
private _axis = vectorNormalized _velocity;
private _turn = (BRMH_CMD_BOMB_TURN * _step) min 1;
for "_i" from 1 to 600 do {
	private _speed = vectorMagnitude _velocity;
	private _along = _axis vectorMultiply (_velocity vectorDotProduct _axis);
	private _across = _velocity vectorDiff _along;
	private _accel = ([0, 0, -9.81] vectorAdd (_along vectorMultiply (-BRMH_CMD_BOMB_DRAG * _speed))) vectorAdd (_across vectorMultiply -_side);
	_axis = vectorNormalized (_axis vectorAdd (((_velocity vectorMultiply (1 / _speed)) vectorDiff _axis) vectorMultiply _turn));
	_velocity = _velocity vectorAdd (_accel vectorMultiply _step);
	_position = _position vectorAdd (_velocity vectorMultiply _step);
	if ((_position # 2) <= getTerrainHeightASL _position) exitWith {};
};
_position
