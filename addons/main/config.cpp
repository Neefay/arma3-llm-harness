class CfgPatches {
	class brmh_main {
		name = "BRMH Harness - probe";
		author = "Nife";
		units[] = {};
		weapons[] = {};
		requiredVersion = 2.18;
		requiredAddons[] = {"cba_main"};
	};
};

class CfgFunctions {
	class BRMH {
		class core {
			file = "\x\brmh\addons\main\functions";
			class preInit {
				preInit = 1;
			};
			class postInit {
				postInit = 1;
			};
			class onFrame {};
			class route {};
			class resolveTargets {};
			class exec {};
			class emit {};
			class out {};
			class sanitize {};
			class onScriptError {};
			class bridgeCall {};
			class register {};
			class guiText {};
		};
	};
};
