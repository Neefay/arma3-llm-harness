/*
	NAME: set_time_weather
	DESCRIPTION: Set the time of day and the weather, for everyone. Night needs moonlight to be playable: with
		full_moon (the default) the date becomes 10 June 2035, a full moon; most other nights are pitch black.
	PARAMETERS:
		0 - hour (NUMBER, default 12): 0 to 23
		1 - minute (NUMBER, default 0): 0 to 59
		2 - overcast (NUMBER, default 0.3): 0 clear to 1 stormy
		3 - fog (NUMBER, default 0): 0 none to 1 thick; 0.2 is a light haze
		4 - rain (NUMBER, default 0): 0 to 1; needs overcast above about 0.7 to show
		5 - full_moon (BOOL, default true): use a full-moon date
	RETURNS: the new date and weather (HASHMAP)
	TARGET: server
	TAGS: time, night, day, weather, fog, rain, overcast, moon, date, environment
	EXAMPLE: {"hour": 23, "minute": 30, "fog": 0.2}
*/
params ["_hour", "_minute", "_overcast", "_fog", "_rain", "_fullMoon"];
if (_hour < 0 or {_hour > 23} or {_minute < 0} or {_minute > 59}) exitWith {
	"ERROR: hour must be 0 to 23 and minute 0 to 59"
};
private _date = [[date # 0, date # 1, date # 2], [2035, 6, 10]] select _fullMoon;
private _new = _date + [floor _hour, floor _minute];
// setDate only changes the machine it runs on: everyone has to run it.
[_new] remoteExec ["setDate", 0];
0 setOvercast (_overcast max 0 min 1);
0 setFog (_fog max 0 min 1);
0 setRain (_rain max 0 min 1);
forceWeatherChange;
createHashMapFromArray [["date", _new], ["overcast", _overcast], ["fog", _fog], ["rain", _rain]]
