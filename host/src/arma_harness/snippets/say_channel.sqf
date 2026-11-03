/*
	Server side of say.sqf (comments are stripped by the host): the custom radio channel for a sender,
	created once per mission, in the sender's colour. _this: [sender, color RGBA].
	Returns the channel id, 0 if none could be created.
*/
params [["_sender", "Claude", [""]], ["_color", [0.95, 0.55, 0.15, 1], [[]], 4]];
if (isNil "brmh_sayChannels") then {
	brmh_sayChannels = createHashMap;
};
private _channel = brmh_sayChannels getOrDefault [_sender, 0];
if (_channel isEqualTo 0) then {
	_channel = radioChannelCreate [_color, _sender, _sender, [], true];
	brmh_sayChannels set [_sender, _channel];
};
_channel
