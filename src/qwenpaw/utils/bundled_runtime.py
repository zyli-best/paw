"""Request-local portable runtimes; never activate or mutate the server env."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
from typing import Any
from uuid import uuid4

from filelock import FileLock

from ..config.config import BundledRuntimesConfig
from ..config.context import describe_default_relative_file_dir
from ..config.shell_policy import force_direct_subprocess_sync_enabled


class BundledRuntimeError(RuntimeError):
    """An explicitly enabled runtime could not be prepared; no host fallback."""


@dataclass(frozen=True)
class RequestRuntimes:
    root: Path
    info: dict[str, dict[str, str]]
    path_entries: tuple[str, ...]
    environment: dict[str, str]
    remove_keys: frozenset[str]

    def process_env(self, base: dict[str, str]) -> dict[str, str]:
        """PATH names and runtime variables are case-insensitive on Windows."""
        replaced = self.remove_keys | {key.upper() for key in self.environment}
        existing_path = next(
            (v for k, v in base.items() if k.upper() == "PATH"),
            "",
        )
        env = {
            k: v
            for k, v in base.items()
            if k.upper() not in replaced and k.upper() != "PATH"
        }
        env.update(self.environment)
        env["PATH"] = os.pathsep.join((*self.path_entries, existing_path))
        return env


current_runtimes: ContextVar[RequestRuntimes | None] = ContextVar(
    "bundled_runtimes",
    default=None,
)


def supported_request(request: dict[str, Any]) -> bool:
    return (
        sys.platform == "win32"
        and struct.calcsize("P") == 8
        and not request.get("is_coding_mode", False)
        and force_direct_subprocess_sync_enabled()
    )


def runtime_directory() -> Path:
    """Server-controlled override supports source checkouts, not Chat input."""
    override = os.environ.get("QWENPAW_BUNDLED_RUNTIMES_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "runtimes"
    return Path(__file__).resolve().parents[3] / "runtimes"


@lru_cache(maxsize=8)
def _read_manifest(path: str, mtime_ns: int, size: int) -> dict:
    del mtime_ns, size  # cache invalidation follows the actual manifest file
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or data.get("platform") != "windows-x86_64"
    ):
        raise ValueError("Unsupported runtime manifest/platform")
    return data


_ENTRIES = {
    "python": {"executable": "python/python.exe"},
    "nodejs": {
        "executable": "node/node.exe",
        "npm_cli": "node/node_modules/npm/bin/npm-cli.js",
        "npx_cli": "node/node_modules/npm/bin/npx-cli.js",
    },
    "git": {"executable": "git/cmd/git.exe", "bash": "git/bin/bash.exe"},
}


def bundle_status() -> dict:
    root = runtime_directory()
    result = {
        "directory": str(root),
        "supported_platform": sys.platform == "win32" and struct.calcsize("P") == 8,
        "runtimes": {},
    }
    try:
        path = root / "manifest.json"
        stat = path.stat()
        manifest = _read_manifest(str(path), stat.st_mtime_ns, stat.st_size)
        manifest_error = ""
    except (OSError, ValueError, TypeError) as exc:
        manifest, manifest_error = {}, str(exc)
    for kind, entries in _ENTRIES.items():
        try:
            version = manifest["runtimes"][kind]["version"]
            if kind == "python" and not version.startswith("3.11."):
                raise ValueError("Bundled Python must be 3.11.x")
            if kind == "nodejs" and not version.startswith("22."):
                raise ValueError("Bundled Node.js must be 22.x")
            for relative in entries.values():
                path = root / relative
                if not path.resolve().is_relative_to(root) or not path.is_file():
                    raise FileNotFoundError(path)
            error = manifest_error
        except (KeyError, AttributeError, OSError, ValueError, TypeError) as exc:
            version, error = "", manifest_error or str(exc)
        result["runtimes"][kind] = {
            "available": not error,
            "version": version,
            "error": error,
            **{key: str(root / relative) for key, relative in entries.items()},
        }
    return result


def _inside(root: Path, path: Path) -> Path:
    if not path.resolve().is_relative_to(root):
        raise BundledRuntimeError(f"Environment path escapes work directory: {path}")
    return path


def _write_json(path: Path, data: dict) -> None:
    temporary = path.with_name(f".{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _run(args: list[str], env: dict[str, str]) -> dict:
    result = subprocess.run(
        args,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise BundledRuntimeError(
            f"Runtime preparation failed: {args[0]}: {result.stderr[-2000:]}",
        )
    return json.loads(result.stdout) if result.stdout.strip() else {}


def _prepare_python(
    root: Path, managed: Path, status: dict, state: dict, env: dict[str, str]
) -> dict[str, str]:
    base = Path(status["executable"])
    directory = _inside(root, managed / "python")
    python = _inside(root, directory / "Scripts/python.exe")
    stamp = {
        "base": str(base),
        "version": status["version"],
        "size": base.stat().st_size,
        "mtime_ns": base.stat().st_mtime_ns,
    }
    if directory.exists():
        if state.get("python") != stamp or not all(
            _inside(root, directory / relative).is_file()
            for relative in (
                "Scripts/python.exe",
                "pyvenv.cfg",
                "Lib/site-packages/pip/__init__.py",
            )
        ):
            raise BundledRuntimeError(
                f"Python environment is incomplete or its base changed: {directory}. "
                "Move this managed environment aside and retry to recreate it.",
            )
    else:
        _run([str(base), "-I", "-B", "-m", "venv", "--copies", str(directory)], env)
        probe = _run(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                "import json,sys,pip; print(json.dumps(dict(base=sys.base_prefix,"
                "prefix=sys.prefix,version='.'.join(map(str,sys.version_info[:3])))))",
            ],
            env,
        )
        if (
            Path(probe["base"]).resolve() != base.parent.resolve()
            or Path(probe["prefix"]).resolve() != directory.resolve()
            or probe["version"] != status["version"]
        ):
            raise BundledRuntimeError(
                f"Python environment validation failed: {directory}"
            )
        state["python"] = stamp
    return {
        "source": "bundled_venv",
        "version": status["version"],
        "executable": str(python),
        "directory": str(python.parent),
        "work_root": str(root),
    }


def prepare_request_runtimes(
    request: dict[str, Any],
    workspace_dir: Path,
    session_id: str | None,
    config: BundledRuntimesConfig,
) -> RequestRuntimes | None:
    """Only selected tools create directories; initialization performs no downloads."""
    selected = [kind for kind in _ENTRIES if getattr(config, kind)]
    if not config.enabled or not selected or not supported_request(request):
        return None
    try:
        statuses = bundle_status()["runtimes"]
        for kind in selected:
            if not statuses[kind]["available"]:
                raise BundledRuntimeError(
                    f"Bundled {kind} is unavailable: {statuses[kind]['error']}"
                )
        if not request.get("sandbox_mounts") and not session_id:
            raise BundledRuntimeError(
                "A session ID is required for the runtime scratch directory"
            )
        root = describe_default_relative_file_dir(
            workspace_dir=workspace_dir,
            session_id=session_id,
            is_coding_mode=False,
            sandbox_mounts=request.get("sandbox_mounts") or [],
            create_session_dir=True,
        ).path.resolve()
        root.mkdir(parents=True, exist_ok=True)
        info, paths, updates, remove = {}, [], {}, set()
        if "python" in selected or "nodejs" in selected:
            managed = _inside(root, root / ".paw-env")
            managed.mkdir(exist_ok=True)
            lock = _inside(root, managed / ".lock")
            with FileLock(str(lock), timeout=60):
                state_file = _inside(root, managed / "state.json")
                state = (
                    json.loads(state_file.read_text(encoding="utf-8"))
                    if state_file.exists()
                    else {}
                )
                if not isinstance(state, dict):
                    raise ValueError(f"Invalid environment state: {state_file}")
                saved_state = dict(state)
                for name in ("tmp", "cache"):
                    _inside(root, managed / name).mkdir(exist_ok=True)
                updates.update(TEMP=str(managed / "tmp"), TMP=str(managed / "tmp"))
                if "python" in selected:
                    remove.update(
                        {
                            "PYTHONHOME",
                            "PYTHONPATH",
                            "PYTHONUSERBASE",
                            "PYTHONSTARTUP",
                            "VIRTUAL_ENV",
                            "CONDA_PREFIX",
                            "PIP_TARGET",
                            "PIP_PREFIX",
                            "PIP_USER",
                        }
                    )
                    cache = _inside(root, managed / "cache/pip")
                    cache.mkdir(exist_ok=True)
                    updates.update(
                        PIP_CACHE_DIR=str(cache),
                        PIP_CONFIG_FILE=os.devnull,
                        PIP_REQUIRE_VIRTUALENV="1",
                        PYTHONNOUSERSITE="1",
                        PYTHONDONTWRITEBYTECODE="1",
                        PYTHONUTF8="1",
                    )
                    child_env = RequestRuntimes(
                        root, {}, (), updates, frozenset(remove)
                    ).process_env(dict(os.environ))
                    # ensurepip must bootstrap a fresh venv before this guard applies.
                    child_env.pop("PIP_REQUIRE_VIRTUALENV", None)
                    info["python"] = _prepare_python(
                        root, managed, statuses["python"], state, child_env
                    )
                    if state != saved_state:
                        _write_json(state_file, state)
                        saved_state = dict(state)
                    paths.append(info["python"]["directory"])
                    updates["VIRTUAL_ENV"] = str(managed / "python")
                if "nodejs" in selected:
                    for name in ("npm-global", "cache/npm"):
                        _inside(root, managed / name).mkdir(exist_ok=True)
                    for name in ("npm-user.npmrc", "npm-global.npmrc"):
                        path = _inside(root, managed / name)
                        if not path.exists():
                            path.touch(exist_ok=False)
                    modules = _inside(root, root / "node_modules")
                    modules.mkdir(exist_ok=True)
                    package = _inside(root, root / "package.json")
                    if not package.exists():
                        _write_json(package, {"private": True})
                    info["nodejs"] = {
                        "source": "bundled",
                        "version": statuses["nodejs"]["version"],
                        "executable": statuses["nodejs"]["executable"],
                        "directory": str(Path(statuses["nodejs"]["executable"]).parent),
                        "npm_cli": statuses["nodejs"]["npm_cli"],
                        "npx_cli": statuses["nodejs"]["npx_cli"],
                        "dependency_dir": str(modules),
                        "work_root": str(root),
                        "npm_global": str(managed / "npm-global"),
                    }
                    paths.extend(
                        (
                            info["nodejs"]["directory"],
                            str(modules / ".bin"),
                            str(managed / "npm-global"),
                        )
                    )
                    remove.update(
                        {
                            "NODE_OPTIONS",
                            "NODE_PATH",
                            "NPM_CONFIG_WORKSPACE",
                            "NPM_CONFIG_WORKSPACES",
                        }
                    )
                    updates.update(
                        NPM_CONFIG_CACHE=str(managed / "cache/npm"),
                        NPM_CONFIG_PREFIX=str(managed / "npm-global"),
                        NPM_CONFIG_GLOBAL="false",
                        NPM_CONFIG_USERCONFIG=str(managed / "npm-user.npmrc"),
                        NPM_CONFIG_GLOBALCONFIG=str(managed / "npm-global.npmrc"),
                    )
                    state["nodejs"] = {"version": statuses["nodejs"]["version"]}
                if state != saved_state:
                    _write_json(state_file, state)
        if "git" in selected:
            info["git"] = {
                **{
                    k: str(v)
                    for k, v in statuses["git"].items()
                    if k in {"executable", "version", "bash"}
                },
                "source": "bundled",
                "directory": str(Path(statuses["git"]["executable"]).parent),
                "work_root": str(root),
            }
            paths.append(info["git"]["directory"])
            remove.add("GIT_EXEC_PATH")
        return RequestRuntimes(root, info, tuple(paths), updates, frozenset(remove))
    except BundledRuntimeError:
        raise
    except Exception as exc:
        raise BundledRuntimeError(f"Cannot prepare bundled runtimes: {exc}") from exc


def render_runtime_instructions(
    infos: dict[str, dict[str, str]], shell: str | None
) -> str:
    """Examples are regenerated from this request's paths and Shell syntax."""
    name = (shell or "cmd.exe").replace("\\", "/").rsplit("/", 1)[-1].lower()
    powershell = name in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}
    posix = name not in {"cmd", "cmd.exe"} and not powershell

    def quoted(value: str) -> str:
        if powershell:
            return "'" + value.replace("'", "''") + "'"
        if posix:
            return shlex.quote(value.replace("\\", "/"))
        return '"' + value + '"'

    def command(executable: str, args: list[str]) -> str:
        return ("& " if powershell else "") + " ".join(map(quoted, [executable, *args]))

    lines = []
    for kind, info in infos.items():
        if info.get("source") not in {"bundled", "bundled_venv"}:
            continue
        root, exe = info["work_root"], info["executable"]
        if not lines:
            lines.extend(
                (
                    "",
                    "## 本轮内置运行时使用规则",
                    f"- 本轮工作根目录：{root}",
                    "- 环境已由后端准备，无需重新创建、激活虚拟环境或初始化 Node 项目。",
                    "- 每条示例单独调用 execute_shell_command，cwd 使用本轮工作根目录。",
                    "- 使用本轮真实路径，不沿用历史挂载路径；安装依赖与执行脚本使用同一套环境。",
                )
            )
        if kind == "python":
            lines.extend(
                (
                    f"- Python（托管虚拟环境）可执行文件：{exe}",
                    f"- Python（托管虚拟环境）所在目录：{info['directory']}",
                    f"- 安装 Python 库示例：`{command(exe, ['-m', 'pip', 'install', 'pandas'])}`",
                    f"- 执行 Python 示例：`{command(exe, ['task.py'])}`",
                    "- 安装库使用上述 Python 的 -m pip，不使用系统 pip。",
                )
            )
        elif kind == "nodejs":
            lines.extend(
                (
                    f"- Node.js（内置）可执行文件：{exe}",
                    f"- Node.js 本地依赖目录：{info['dependency_dir']}",
                    f"- npm 全局工具目录：{info['npm_global']}",
                    f"- 安装 Node 依赖示例：`{command(exe, [info['npm_cli'], 'install', 'axios', '--prefix', root, '--global=false'])}`",
                    f"- 执行 Node 示例：`{command(exe, ['task.js'])}`",
                    "- npm 本地安装显式指定本轮 --prefix；JS 脚本放在本轮项目内以加载其 node_modules。",
                )
            )
        else:
            lines.extend(
                (
                    f"- Git（内置）可执行文件：{exe}",
                    f"- Git Bash 所在路径：{info['bash']}",
                    f"- Git 示例：`{command(exe, ['status'])}`",
                    "- Git/Bash 已提供，无需安装；Git 开关不改变默认 Shell。",
                )
            )
    return "\n".join(lines)
