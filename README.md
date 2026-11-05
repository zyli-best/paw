# Paw Windows 源码与打包

基于 QwenPaw 的定制版本。本仓库保留 Windows 服务、Web 控制台和六个内置智能体需要的源码、资源及构建文件。来源目录保持原样，文件取舍和副本调整见 [复制说明](docs/COPY_REPORT.md)。许可证见 [LICENSE](LICENSE)。

## 1. 初始化 Windows 环境

预先安装 **64 位 Python 3.11.9** 和 **Node.js 22.12+（含 npm）**。Windows 构建版本由 `.python-version` 固定为原环境的 `3.11.9`，两个脚本都会检查完整版本号，不会自动换用 3.12 / 3.13。首次安装需要访问 Python 包索引和 npm registry。

在本目录打开 PowerShell，运行第一个脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-windows.ps1
```

脚本创建本仓库的 `.venv`，按 `requirements-windows.lock.txt` 恢复原环境的全部 Python 依赖版本，再从当前仓库安装项目；根据 `console/package-lock.json` 执行 `npm ci`，并运行 `pip check` 和完整版本对比。可重复执行，支持 Windows PowerShell 5.1 和 PowerShell 7，无需手动激活环境。

Python 锁文件来自原目录 `.venv` 的实际安装版本，共 262 个依赖；当前项目另行安装后，共 263 个包的版本与原环境一致。包括 `setuptools==65.5.0`、`lark-oapi==1.7.2`、`fastmcp==3.4.6`。项目安装使用隔离构建，临时构建依赖不会加入运行环境。两个脚本都会检查版本漂移，不再按宽泛的版本范围自动安装较新依赖。

如果当前 `.venv` 使用其他 Python 或依赖版本，请用以下命令重建，旧环境会先移入忽略目录 `build/venv-backups/`，再创建与原环境版本一致的 3.11.9 环境：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-windows.ps1 -RecreateVenv
```

`pyproject.toml` 的包兼容范围保留上游定义；它不决定本仓库的 Windows 构建版本。

指定 Python，或安装浏览器工具所需的 Chromium：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\init-windows.ps1 -PythonExe "C:\Python311\python.exe" -InstallBrowser
```

Chromium 安装到 Playwright 浏览器缓存，不打进 exe；目标机器使用浏览器技能时也需准备浏览器运行文件。

## 2. 生成 paw.exe

运行第二个脚本：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-paw.ps1
```

脚本调用 `build:prod`（TypeScript 检查 + Vite 生产构建），更新本地 Python 包元数据，按 `paw.spec` 打包，检查前端和内置智能体资源，并执行 `paw.exe cli --help` 验证可执行文件。

```text
dist/
  paw/
    paw.exe
    devcopaw.exe          # 首次调用自动生成的 CLI 别名
    _internal/            # Python、依赖、前端、内置智能体资源
    runtimes/             # 独立的 Python 3.11、Node.js 22 和 PortableGit/Bash
      manifest.json       # 版本、来源、验证结果和逐文件 SHA256
      python/
      node/
      git/
  paw-runtime.zip         # 应用包：根目录只有 paw.exe 和 _internal/
  paw-runtime.zip.sha256
  runtimes.zip            # 工具包：根目录为 manifest.json、python/、node/、git/
  runtimes.zip.sha256
  start-paw.cmd
  stop-paw.cmd
```

**这是目录模式打包，发布时必须带上 `paw.exe` 和完整的 `_internal/`，不能只复制 `paw.exe`。** 可直接发布整个 `dist/paw/`，也可分发两个 ZIP 和启动脚本：先将 `paw-runtime.zip` 和两个 `.cmd` 文件放在同一目录，用启动工具解压应用，再将 `runtimes.zip` 解压到实际 `paw.exe` 同级的 `runtimes/` 目录。使用启动脚本默认布局时，目标为 `paw-runtime/runtimes/`；工具包内部没有额外的 `runtimes/` 包装层。仅使用应用、不启用内置工具时可以暂不解压工具包。

`start-paw.cmd` 不会自动解压 `runtimes.zip`。运行它的 `init` 初始化刷新流程会重建应用目录，因此之后需要重新解压工具包，或预先通过 `QWENPAW_BUNDLED_RUNTIMES_DIR` 指向应用目录外的运行时。

```powershell
# 仅当前端产物与当前源码一致时跳过编译
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-paw.ps1 -SkipFrontend

# 清理 PyInstaller 分析缓存后构建
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-paw.ps1 -Clean

# 复用另外安装了 openpyxl 等包的现有 .venv
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-paw.ps1 -AllowExtraPackages
```

默认构建要求依赖集合与锁文件完全一致。`-AllowExtraPackages` 仅允许额外安装的包，仍检查 Python 的精确版本和全部锁定依赖版本；缺包或版本不一致仍会停止。此参数可与 `-SkipFrontend`、`-Clean` 组合使用，不会重建 `.venv`。

构建脚本只使用当前仓库的 `.venv`，构建输出位于 `build/` 和 `dist/`。
若曾在 `dist/paw/` 中运行应用并产生配置，重建前先将运行数据备份到 `dist/` 外；脚本检测到这类数据时会停止，以免打包覆盖它们。日常使用建议将发布目录放在源码仓库外。

随包工具由 `scripts/bundled-runtimes.lock.json` 锁定为 Windows x64：Python **3.11.18**（python-build-standalone `20261026` 的 `install_only_stripped`，支持 pip/venv）、Node.js **22.23.4**（npm/npx **10.9.9**）和 PortableGit **2.56.0.windows.4**（含 Bash）。它们独立于用于构建 `paw.exe` 的 Python 3.11.9。构建时从上游下载、校验 SHA256 并保留发行包中的许可证；下载缓存在 `build/runtime-downloads/`，有效缓存可离线复用。

单独准备或验证随包工具：

```powershell
.\.venv\Scripts\python.exe scripts\prepare-bundled-runtimes.py --output build\runtime-preview\runtimes
.\.venv\Scripts\python.exe scripts\prepare-bundled-runtimes.py --verify-only --output dist\paw\runtimes
```

已有应用 ZIP 时，也可保留现有应用二进制，单独生成应用包和工具包。输入 ZIP 与输出应用 ZIP 必须使用不同路径：

```powershell
.\.venv\Scripts\python.exe scripts\package-paw-runtime.py --base-archive dist\paw-runtime.zip --runtime-dir runtimes --output dist\paw-runtime-repacked.zip --runtimes-output dist\runtimes.zip
```

默认生成 `paw-runtime.zip`（仅 `paw.exe`、`_internal/`）和 `runtimes.zip`（仅 `manifest.json`、`python/`、`node/`、`git/`）。两份 ZIP 各有同名 `.sha256` 校验文件。打包时检查运行时逐文件 SHA256、两个 ZIP 的目录结构及 CRC，全部通过后才替换已有发布包；源码和 EXE 无需因拆分 ZIP 而修改。

验证会在 `build/` 的临时目录创建 Python 虚拟环境、离线安装本地测试包，测试 Node 的离线项目依赖安装及 Git/Bash 执行，确认没有修改基础运行时。Windows 非 Coding、直接 subprocess 场景的开关接口、Chat 环境初始化和动态调用示例见 [内置运行时说明](docs/bundled-runtimes.md)。总开关默认关闭；源码运行可用 `scripts/prepare-bundled-runtimes.py --output runtimes` 准备本地工具。

## 模型配置与启动

此副本已移除源码中的硬编码 API Key。启动前按实际服务设置环境变量；命令行选项仍可覆盖它们：

```powershell
$env:OPENAI_BASE_URL = "https://your-model-service.example/v1"
$env:OPENAI_MODEL = "your-model-name"
$env:OPENAI_API_KEY = "your-api-key"

# 源码运行
.\.venv\Scripts\python.exe .\main.py --host 127.0.0.1 --port 8088

# 或运行构建结果
.\dist\paw\paw.exe --host 127.0.0.1 --port 8088
```

Web 控制台地址为 `http://127.0.0.1:8088`。运行数据和密钥位于应用目录下的 `.devco_paw/`、`.devco_paw.secret/`，不应提交到 Git。

Langfuse 会话上传默认关闭。启用时设置 `QWENPAW_SESSION_DELTA_LANGFUSE_ENABLED=1`、`QWENPAW_SESSION_DELTA_LANGFUSE_HOST`、`QWENPAW_SESSION_DELTA_LANGFUSE_PUBLIC_KEY`、`QWENPAW_SESSION_DELTA_LANGFUSE_SECRET_KEY`。边缘模型密钥使用 `QWENPAW_EDGE_CLOUD_EDGE_API_KEY`。

云边端协同明确使用 RouterAgent、VerifyAgent、CloudAgent、EdgeAgent、DeviceAgent。Router/Verify/Cloud 复用原 Agent 已加载的模型；Device 与 Edge 通过 Chat 的 `request_context.edge_cloud.device/edge` 分别配置模型，互不共享或回退。简单无工具任务交 Device 直接返回；配置轮数内的基础文件任务交 Device 并校验；检查后可独立执行的单 Skill 交 Edge 并校验；复杂、创造性、多 Agent/Skill 联动和负反馈任务交 Cloud，不校验。端边只接收完整任务与本轮执行记录，原 Scroll、session 和 Langfuse 链路沿用。协同默认关闭，通过 `--edge-cloud-enabled 1/0` 或 Chat 中的 `edge_cloud.enabled` 开关；端侧工具调用轮数默认 2，可用 `--edge-cloud-device-max-tool-rounds N`、`QWENPAW_EDGE_CLOUD_DEVICE_MAX_TOOL_ROUNDS` 或 Chat 中的 `device.max_tool_rounds` 调整为正整数。旧边云兼容接口已移除。完整 Chat 参数示例见 [云边端协同方案](docs/云边端大模型多Agent协同方案.md)。

`start-paw.cmd`、`stop-paw.cmd` 原样保留。前者的 `init` 参数会重建初始化配置并清理密钥目录；后者会停止本机的 Paw 进程。日常也可直接运行上述 `paw.exe` 命令。

## 提交到 Git

提交源码、脚本、`requirements-windows.lock.txt`、`requirements-build.txt`、`console/package-lock.json` 和 `src/qwenpaw/agents/bundled_workspaces.zip`。`.gitignore` 排除了虚拟环境、前端依赖、构建产物、日志和本机配置，必需资源可正常提交。

```powershell
git status --short
git add .
git commit -m "Add Paw Windows sources and build scripts"
```

此任务未执行提交或推送。
