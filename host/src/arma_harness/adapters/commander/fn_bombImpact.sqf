// Where a bomb released now would land, unguided. The engine flies a bomb as a missile: it has an axis, starting along
// the aircraft's velocity and turning toward its own; drag acts along the axis, and its side friction (the ammo's
// maneuvrability) damps any velocity across it, which holds the fall back like lift. Fitted to the Mk82's flight
// (host/tests/spikes/cas/spike_bomb_drag.py): within 25 m of the real throw of 1.8-1.9 km. Drag alone was 300 m short.
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
