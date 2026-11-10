// "Two bombs", as the pilot says it.
params ["_count"];
format ["%1 %2", ["One", "Two", "Three", "Four"] select ((_count - 1) min 3), ["bombs", "bomb"] select (_count isEqualTo 1)]
