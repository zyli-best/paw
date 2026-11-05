"""Offline proof against the separately prepared Windows runtime distribution."""

import json
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest
from agentscope.message import ToolResultState

from qwenpaw.config.config import BundledRuntimesConfig
from qwenpaw.config.context import (
    current_request_context,
    current_shell_command_executable,
)
from qwenpaw.utils import bundled_runtime as br


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "win32", reason="Windows portable distribution")
async def test_real_offline_installs_use_current_project_and_leave_base_unchanged(
    monkeypatch, tmp_path
):
    bundle = Path(__file__).resolve().parents[1] / "runtimes"
    if not (bundle / "manifest.json").is_file():
        pytest.skip("Prepare the locked runtime distribution first")
    from qwenpaw.agents.tools import shell

    monkeypatch.setenv("QWENPAW_BUNDLED_RUNTIMES_DIR", str(bundle))
    monkeypatch.setenv("QWENPAW_FORCE_DIRECT_SUBPROCESS_SYNC", "1")
    monkeypatch.setenv("QWENPAW_WINDOWS_DIRECT_SHELL_GUARD", "off")
    monkeypatch.setenv("QWENPAW_WINDOWS_DIRECT_SHELL_LLM_GUARD", "off")

    def inventory():
        return {
            p.relative_to(bundle).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in bundle.rglob("*")
            if p.is_file()
        }

    before = inventory()
    root = tmp_path / "项目 空格"
    request = {
        "sandbox_mounts": [str(root)],
        "session_id": "offline",
        "is_coding_mode": False,
    }
    state = br.prepare_request_runtimes(
        request, tmp_path / "workspace", "offline", BundledRuntimesConfig(enabled=True)
    )
    assert state is not None
    assert (
        br.prepare_request_runtimes(
            request,
            tmp_path / "workspace",
            "offline",
            BundledRuntimesConfig(enabled=True),
        )
        == state
    )
    token = br.current_runtimes.set(state)
    request_token = current_request_context.set(request)
    shell_token = current_shell_command_executable.set("cmd.exe")

    # Existing host installations/configuration must not redirect selected tools.
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "host-python"))
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "host-python-libraries"))
    monkeypatch.setenv("NODE_OPTIONS", "--require=nonexistent-host-hook")
    monkeypatch.setenv("NPM_CONFIG_PREFIX", str(tmp_path / "host-node-global"))

    async def execute(exe, *args):
        # All file arguments are quoted, including paths with Chinese/spaces.
        command = " ".join('"' + str(arg) + '"' for arg in (exe, *args))
        result = await shell.execute_shell_command(command)
        text = "\n".join(
            block.text for block in result.content if hasattr(block, "text")
        )
        assert result.state == ToolResultState.SUCCESS, text
        assert "Command failed" not in text, text
        return text

    try:
        wheel = root / "paw_dep_probe-1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("paw_dep_probe.py", "VALUE = 'python-isolated'\n")
            archive.writestr(
                "paw_dep_probe-1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: paw-dep-probe\nVersion: 1.0\n",
            )
            archive.writestr(
                "paw_dep_probe-1.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            archive.writestr("paw_dep_probe-1.0.dist-info/RECORD", "")
        await execute("pip", "install", "--no-index", "--no-deps", wheel)
        (root / "task.py").write_text(
            "import paw_dep_probe,sys; print(paw_dep_probe.VALUE); print(sys.executable)\n",
            encoding="utf-8",
        )
        text = await execute("python", "task.py")
        assert (
            "python-isolated" in text
            and str(root / ".paw-env/python/Scripts/python.exe") in text
        )
        assert (root / ".paw-env/python/Lib/site-packages/paw_dep_probe.py").is_file()
        assert not (bundle / "python/Lib/site-packages/paw_dep_probe.py").exists()

        package = root / "probe-package"
        package.mkdir()
        (package / "package.json").write_text(
            json.dumps(
                {"name": "paw-dep-probe", "version": "1.0.0", "main": "index.js"}
            ),
            encoding="utf-8",
        )
        (package / "index.js").write_text(
            "module.exports='node-isolated';\n", encoding="utf-8"
        )
        tarball = root / "probe.tgz"
        with tarfile.open(tarball, "w:gz") as archive:
            archive.add(package, arcname="package")
        node = state.info["nodejs"]["executable"]
        await execute(
            "npm",
            "install",
            tarball,
            "--prefix",
            root,
            "--global=false",
            "--offline",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        )
        (root / "task.js").write_text(
            "console.log(require('paw-dep-probe')); console.log(process.execPath);\n",
            encoding="utf-8",
        )
        text = await execute(node, "task.js")
        assert "node-isolated" in text and node in text
        assert (root / "node_modules/paw-dep-probe/index.js").is_file()
        assert not (bundle / "node/node_modules/paw-dep-probe").exists()
        assert "git version" in await execute(
            state.info["git"]["executable"], "--version"
        )
        assert "GNU bash" in await execute(state.info["git"]["bash"], "--version")

        denied = await shell.execute_shell_command(f'"{sys.executable}" task.py')
        assert denied.state == ToolResultState.ERROR
        assert denied.metadata["guard"] == "bundled_runtime_path"
        retried = await shell.execute_shell_command(
            denied.metadata["recommended_command"]
        )
        assert retried.state == ToolResultState.SUCCESS
        assert "python-isolated" in str(retried.content)

        # Verify actual PowerShell quoting too, with the same runtime selection.
        current_shell_command_executable.set("powershell.exe")
        text = await execute("python", "task.py")
        assert "python-isolated" in text
        text = await execute("node", "task.js")
        assert "node-isolated" in text
    finally:
        current_shell_command_executable.reset(shell_token)
        current_request_context.reset(request_token)
        br.current_runtimes.reset(token)
    assert inventory() == before
