/*
	NAME: BRMH_fnc_guiText
	DESCRIPTION: Text snapshot of the user interface: every open display with its controls' class,
		text, position and visibility. Meant for reading the screen without pixels.
	PARAMETERS:
		0 - (OPTIONAL) Only visible controls: shown and not fully faded (BOOL) - Default: true
		1 - (OPTIONAL) Maximum controls per display (NUMBER) - Default: 300
		2 - (OPTIONAL) Only controls with readable text: non-empty and not a texture path or
			procedural texture such as "\a3\...paa" or "#(argb,...)" (BOOL) - Default: false
	USAGE:
		[] call BRMH_fnc_guiText;
		[true, 100, true] call BRMH_fnc_guiText; // visible controls that display text
	RETURNS: [[idd, [[idc, class, type, text, [x, y, w, h], fade], ...]], ...] (ARRAY)
	ENVIRONMENT: Machines with an interface
*/
params [["_visibleOnly", true, [true]], ["_maxControls", 300, [0]], ["_textOnly", false, [true]]];

allDisplays apply {
	private _controls = (allControls _x) select {
		(not _visibleOnly or {
			ctrlShown _x and {
				ctrlFade _x < 1
			}
		}) and {
			not _textOnly or {
				private _text = ctrlText _x;
				_text isNotEqualTo "" and {
					not ((_text select [0, 1]) in ["\", "#"])
				} and {
					not (".paa" in toLower _text)
				}
			}
		}
	};
	[
		ctrlIDD _x,
		(_controls select [0, _maxControls]) apply {
			[
				ctrlIDC _x,
				ctrlClassName _x,
				ctrlType _x,
				ctrlText _x,
				(ctrlPosition _x) apply {
					round (_x * 1000) / 1000
				},
				round ((ctrlFade _x) * 100) / 100
			]
		}
	]
}
