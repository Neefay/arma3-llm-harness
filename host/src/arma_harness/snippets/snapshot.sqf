/*
	In-engine snapshot request (runs on a rendering client). Comments are stripped by the host.
	_this: [path, camPosATL or [], camTargetATL or [], fov, maxWidth, hideHud]
	With a camera, the main view switches to it, is captured after a few frames, and is restored when
	the extension reports "frame_done".
*/
params ["_path", ["_camPos", []], ["_camTarget", []], ["_fov", 0.75], ["_maxWidth", 0], ["_hideHud", false]];

if (isNil "brmh_snapEh") then {
	brmh_snapEh = addMissionEventHandler ["ExtensionCallback", {
		params ["_name", "_function"];
		if (_name isEqualTo "brmh" and {
			_function isEqualTo "frame_done"
		}) then {
			if (not isNil "brmh_snapCam") then {
				brmh_snapCam cameraEffect ["terminate", "back"];
				camDestroy brmh_snapCam;
				brmh_snapCam = nil;
			};
			if (not isNil "brmh_snapHud") then {
				showHUD brmh_snapHud;
				brmh_snapHud = nil;
			};
		};
	}];
};

private _delay = 0;
if (_hideHud) then {
	brmh_snapHud = shownHUD;
	showHUD [false, false, false, false, false, false, false, false, false, false, false];
	_delay = 2;
};
if (_camPos isNotEqualTo []) then {
	if (not isNil "brmh_snapCam") then {
		brmh_snapCam cameraEffect ["terminate", "back"];
		camDestroy brmh_snapCam;
	};
	brmh_snapCam = "camera" camCreate _camPos;
	if (_camTarget isNotEqualTo []) then {
		brmh_snapCam camSetTarget _camTarget;
	};
	brmh_snapCam camSetFov _fov;
	brmh_snapCam camCommit 0;
	brmh_snapCam cameraEffect ["internal", "back"];
	showCinemaBorder false;
	_delay = 4;
};
("brmh" callExtension ["gfx:frame", [_path, _delay, _maxWidth]]) params ["_result", "_code"];
[_result, _code]
