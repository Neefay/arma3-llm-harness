params ["_soldiers", "_object", "_point", ["_through", "VIEW"]];
(_soldiers findIf {
	([_x, _through, _object] checkVisibility [eyePos _x, _point]) > 0.3
}) >= 0
