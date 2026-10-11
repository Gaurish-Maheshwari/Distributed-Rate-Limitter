"""Loads Lua scripts once and runs them with EVALSHA (falls back to EVAL)."""
import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from redis.asyncio import Redis
from redis.exceptions import NoScriptError

LUA_DIR = Path(__file__).parent / "lua"


@dataclass(frozen=True)
class LuaScript:
    name: str
    source: str
    sha: str


@lru_cache(maxsize=None)
def load_script(name: str) -> LuaScript:
    source = (LUA_DIR / name).read_text()
    return LuaScript(name, source, hashlib.sha1(source.encode()).hexdigest())


def all_scripts() -> list[LuaScript]:
    return [load_script(p.name) for p in sorted(LUA_DIR.glob("*.lua"))]


async def run_script(redis: Redis, script: LuaScript, keys: list[str], args: list) -> list:
    """Run a script atomically. EVALSHA is cheap; on a cold Redis, EVAL loads + caches it."""
    try:
        return await redis.evalsha(script.sha, len(keys), *keys, *args)
    except NoScriptError:
        return await redis.eval(script.source, len(keys), *keys, *args)
