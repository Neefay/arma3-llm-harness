params ["_man"];
(_man getVariable ["ace_medical_medicClass", parseNumber (_man getUnitTrait "medic")]) > 0
