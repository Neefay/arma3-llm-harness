/*
	Server side of say.sqf and of listening (comments are stripped by the host): the custom radio channel named after
	an agent, created once per mission in its colour, with every player in it. Players type to the agent there without
	starting with its name, and its replies appear there. Re-run on every listen, so players who joined since are
	added. _this: [sender, color RGBA].
	Returns the channel id (1 to 10), 0 if none could be created (a mission has ten custom channels at most).
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
if (_channel > 0) then {
	_channel radioChannelAdd allPlayers;
};
_channel
