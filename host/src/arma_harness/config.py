"""Locations and configuration.

Harness home (runtime state, never in the repo): ``%LOCALAPPDATA%\\arma-harness`` or ``$BRMH_HOME``.
It must match what the in-game bridge computes (python/bridge.py ``harness_home``).

Configuration: ``harness.toml``, looked up in ``$BRMH_CONFIG``, then the repo root, then the home.
"""
from __future__ import annotations

import os
import tomllib
import winreg
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def harness_home() -> Path:
    override = os.environ.get("BRMH_HOME")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "arma-harness"


class Home:
    """Well-known folders under the harness home."""

    def __init__(self, root: Path | None = None):
        self.root = root or harness_home()

    def _dir(self, name: str) -> Path:
        p = self.root / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def sessions(self) -> Path:
        return self._dir("sessions")

    @property
    def mods(self) -> Path:
        return self._dir("mods")

    @property
    def server_root(self) -> Path:
        return self._dir("server_root")

    @property
    def runs(self) -> Path:
        return self._dir("runs")

    @property
    def captures(self) -> Path:
        return self._dir("captures")

    @property
    def logs(self) -> Path:
        return self._dir("logs")

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"


def find_arma_dir() -> Path:
    """The Arma 3 install: $ARMA3_DIR, then the registry, then the default Steam path."""
    env = os.environ.get("ARMA3_DIR")
    if env and (Path(env) / "arma3_x64.exe").exists():
        return Path(env)
    for hive, key in [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\bohemia interactive\arma 3"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\bohemia interactive\arma 3"),
    ]:
        try:
            with winreg.OpenKey(hive, key) as k:
                path = Path(winreg.QueryValueEx(k, "main")[0])
                if (path / "arma3_x64.exe").exists():
                    return path
        except OSError:
            continue
    default = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Arma 3")
    if (default / "arma3_x64.exe").exists():
        return default
    raise FileNotFoundError("Arma 3 not found; set ARMA3_DIR or [arma].dir in harness.toml")


@dataclass
class MissionProfile:
    name: str
    source: Path
    mods: list[str] = field(default_factory=list)
    client_mods: list[str] = field(default_factory=list)
    hc_mods: list[str] | None = None
    adapters: list[str] = field(default_factory=list)
    skip_lobby: bool = True
    allow_recompile: bool = True
    overrides: dict = field(default_factory=dict)

    @property
    def folder_name(self) -> str:
        return self.source.name


@dataclass
class Config:
    arma_dir: Path
    missions: dict[str, MissionProfile]
    default_mission: str = "selftest"
    paths: list[Path] = field(default_factory=list)
    home: Home = field(default_factory=Home)

    def mission(self, name: str | None = None) -> MissionProfile:
        name = name or self.default_mission
        if name in self.missions:
            return self.missions[name]
        raise KeyError(f"unknown mission profile {name!r}; known: {sorted(self.missions)}")

    def mod_path(self, mod: str) -> Path:
        """'@CBA_A3' -> Workshop folder; '@brmh' -> the built harness mod; absolute paths as-is."""
        p = Path(mod)
        if p.is_absolute():
            return p
        built = self.home.mods / mod
        if built.exists():
            return built
        ws = self.arma_dir / "!Workshop" / mod
        if ws.exists():
            return ws
        local = self.arma_dir / mod
        if local.exists():
            return local
        raise FileNotFoundError(f"mod {mod!r} not found (looked in {self.home.mods}, Workshop, Arma dir)")


def config_paths() -> list[Path]:
    """Config files in merge order (later files override earlier ones, profile by profile):
    the repo's ``harness.toml``, the git-ignored ``harness.local.toml`` next to it, the harness
    home's ``harness.toml``, then ``$BRMH_CONFIG``."""
    candidates = [REPO_ROOT / "harness.toml", REPO_ROOT / "harness.local.toml", harness_home() / "harness.toml"]
    if os.environ.get("BRMH_CONFIG"):
        candidates.append(Path(os.environ["BRMH_CONFIG"]))
    return [p for p in candidates if p.exists()]


def load_config(paths: list[Path] | None = None) -> Config:
    paths = config_paths() if paths is None else paths
    arma: dict = {}
    harness: dict = {}
    raw_missions: dict[str, tuple[Path, dict]] = {}
    for path in paths:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        arma.update(data.get("arma", {}))
        harness.update(data.get("harness", {}))
        for name, m in data.get("missions", {}).items():
            raw_missions[name] = (path.parent, m)
    arma_dir = Path(arma["dir"]) if arma.get("dir") else find_arma_dir()
    missions = {}
    for name, (base, m) in raw_missions.items():
        src = Path(m["source"])
        if not src.is_absolute():
            src = (base / src).resolve()
        missions[name] = MissionProfile(
            name=name,
            source=src,
            mods=list(m.get("mods", [])),
            client_mods=list(m.get("client_mods", m.get("mods", []))),
            hc_mods=list(m["hc_mods"]) if "hc_mods" in m else None,
            adapters=list(m.get("adapters", [])),
            skip_lobby=bool(m.get("skip_lobby", True)),
            allow_recompile=bool(m.get("allow_recompile", True)),
            overrides=dict(m.get("overrides", {})),
        )
    default = harness.get("default_mission", "selftest")
    return Config(arma_dir=arma_dir, missions=missions, default_mission=default, paths=paths)
