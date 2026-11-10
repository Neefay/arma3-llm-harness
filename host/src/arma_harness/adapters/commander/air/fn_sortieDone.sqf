// The seek-and-destroy waypoint is finished: the pilot has nothing more he knows of to attack there.
params ["_machine"];
(currentWaypoint (_machine get "GROUP")) > (_machine get "WAYPOINT")
