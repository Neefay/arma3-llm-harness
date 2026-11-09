/*
	Two one-way feeds for a human observer. They write to the game's chat and map, and nothing reads them back,
	so they can't help the commander.
*/
params [["_text", "", [""]]];
[_text] remoteExec ["systemChat", 0];
true
