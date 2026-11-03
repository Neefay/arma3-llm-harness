/*
	Show a message to players (comments are stripped by the host).
	_this: [text, sender, hint, channel, color ("#rrggbb", the sender's colour)]
	channel is a custom radio channel made by say_channel.sqf on the server (radioChannelCreate is
	server-only), so the line reads "<sender>: <text>" in the chat feed in its own colour. 0 falls back
	to systemChat. "hint" also shows the text as a hint box (for longer answers).
*/
params [["_text", "", [""]], ["_sender", "Claude", [""]], ["_hint", false, [true]], ["_channel", 0, [0]], ["_color", "#f28c26", [""]]];
if (not hasInterface) exitWith {
	false
};
if (_channel > 0) then {
	_channel radioChannelAdd [player];
	// customChat fires HandleChatMessage; the chat observer skips messages posted while this is set.
	brmh_saying = true;
	player customChat [_channel, _text];
	brmh_saying = nil;
} else {
	systemChat format ["%1: %2", _sender, _text];
};
if (_hint) then {
	hintSilent parseText format ["<t size='1.1' color='%3'>%1</t><br/>%2", _sender, _text, _color];
} else {
	// Clears a "thinking..." acknowledgement left by the host's listen.
	hintSilent "";
};
true
