# 来源分析与复制说明

来源：`D:\project\qwenpaw_launch_script\paw_20_10`。目标：本仓库。所有复制、调整和构建均只写入目标，来源不运行安装、构建或代码修改。

## 保留内容

| 文件 / 目录 | 必需原因 |
| --- | --- |
| `src/qwenpaw/` | 后端模块及动态导入入口，不能只保留入口直接引用的文件 |
| `agents/skills/`、`agents/md_files/`、`tokenizer/`、`security/**` | 初始化需要的技能、提示词、词法、安全规则和工具资源 |
| `agents/bundled_workspaces.zip` | 六个定制智能体的定义、专用技能及工具，约 28 MiB |
| `console/src/`、`console/public/`、前端配置 | 控制台源码和构建输入；测试源码也保留，TypeScript 会检查整个 `src/` |
| `console/package.json`、`package-lock.json`、`.npmrc` | 使用锁文件安装前端依赖 |
| `website/public/docs/*.md` → `src/qwenpaw/docs/` | 应用内文档资源，无需构建整个宣传网站 |
| `main.py`、`paw.spec` | Windows 服务入口和 PyInstaller 构建配置 |
| `pyproject.toml`、`setup.py`、`LICENSE`、`.python-version`、`.gitattributes` | Python 包定义、版权和源码约定 |
| `start-paw.cmd`、`stop-paw.cmd` | 原版发布启动工具，原样保留，与输出的 `paw-runtime.zip` 兼容 |
| `scripts/init-windows.ps1`、`scripts/build-paw.ps1`、`requirements-build.txt` | 新增的两个脚本与打包工具版本定义 |

首次导入复制 **1,864 个文件，60.75 MiB**，之后只在副本中清理。六个内置智能体为 `code_generator`、`code_keeper`、`firmware_planner`、`personal_assistant`、`svn_guard`、`vuln_scan`。`ExcelConvert_3.1.exe` 是技能附带的业务工具，予以保留；其他依赖外部业务工具的技能仍需准备其运行条件。

## 未复制内容

| 来源内容 | 判断 |
| --- | --- |
| `.venv/`、`node_modules/` | 本机安装产物，由初始化脚本重新安装 |
| `build/`、`dist/`、`console/dist/`、`paw.zip` | 可重新生成的旧产物；`paw.zip` 约 473 MiB，不适合源码提交 |
| `.devco_paw/`、`.devco_paw.secret/`、`logs/`、`session_tmp/` | 本机运行数据、凭据和日志 |
| `.git/`、IDE 配置、各类缓存、`.github/` | 保留目标 Git 历史，来源配置不是此构建流程的输入 |
| `start-paw_1.cmd`、两个带“副本”的 `.cmd` | 历史重复文件，正式版本已保留 |
| `scripts/pack/`、`scripts/pack-tauri/`、`console/src-tauri/` | 另一套桌面、Tauri、macOS 构建，当前流程不使用，无需 Rust 工具链 |
| `plugins/` | 可选插件源码仓库；实际运行插件目录是 `WORKING_DIR/plugins` |
| `llmrouter_addons/` | 仅有缓存 / 空目录，没有需要保留的源码 |
| 网站其他文件、Docker / `deploy/` | 网站和容器部署，不属于 Windows exe 目标 |
| 原版 `tests/`、`e2e/`、`example/`、开发文档、个人笔记 | 开发和示例资料，不是运行 / 打包输入 |

`console/package.json` 保留上游命令定义，其中 Tauri 命令不属于精简仓库支持的流程。

## 仅对目标副本的调整

1. `main.py`：模型、边缘模型、Langfuse 密钥及服务地址改读环境变量，命令行优先级保留，Langfuse 默认关闭。
2. `observability/session_delta_langfuse.py`：移除备用硬编码凭据和内网地址，默认关闭上传，显式配置后仍可启用。
3. 技能文档 `lcfc_workflow_generator-zh/references/protocol.md`：七处实际密钥示例替换成 `YOUR_API_KEY`。
4. 内置 ZIP：去掉 21 个媒体 / 文件索引 / 结果条目和 16 个缓存 / 锁 / 历史备份条目，12 个记忆 / 用户资料文件重置为空模板。原有会话和定时任务列表为空。
5. `paw.spec`：更正输出目录说明，删除重复添加 ZIP 的代码，缺少前端时直接报错。
6. `.gitignore`：忽略本机数据和产物，允许必需 ZIP、前端锁文件、技能 `AGENTS.md` 和包内 JSON 提交。
7. 首次整理使用 Python 3.12 时曾将 setuptools 改为 80.9.0，以避开 65.5.0 的 `pkgutil.ImpImporter` 报错。按用户要求恢复原环境后，当前已固定 Python 3.11.9 和原版 `setuptools==65.5.0`，不再保留这次升级。`pkg_resources` 的后续弃用变化见 [setuptools 版本记录](https://setuptools.pypa.io/en/latest/history.html)。
8. 构建时的应用工作目录指向 `build/packaging-data`，避免依赖分析读取本机已有配置；重建前检查 `dist/paw/` 的运行数据，存在实际数据时停止，防止输出目录被覆盖而丢失配置。
9. 按原环境固定 Windows 构建为 64 位 Python `3.11.9`：`.python-version` 记录完整版本，两个脚本读取并检查实际解释器，不接受其他版本。初始化脚本的 `-RecreateVenv` 会先将旧环境备份到 `build/venv-backups/` 再重建。包自身的兼容范围保留上游定义。
10. `requirements-windows.lock.txt` 从原目录虚拟环境的安装元数据导出，固定全部 262 个第三方包；项目 `qwenpaw==2.0.0` 从当前仓库安装。`scripts/check-windows-env.py` 检查完整版本集合，初始化和构建均会拒绝版本漂移。锁文件不含原路径、安装 URL 或凭据。原环境没有单独安装 wheel，项目元数据安装采用隔离构建，不将临时构建包加入运行环境。

原打包说明曾写“单文件”，但实际是 `EXE(exclude_binaries=True) + COLLECT` 的目录模式。这里保留工作方式并明确完整发布目录，避免只分发不能独立运行的 `paw.exe`。

## 首次整理验证记录

首次整理曾使用的验证环境：Windows 11，64 位 Python 3.12.9，Node.js 24.15.0，npm 11.12.1，Windows PowerShell 5.1。该 Python 版本随后按用户要求对齐为原环境的 3.11.9；当前构建使用 `.python-version` 的精确版本。

- 初始化脚本实际执行成功：新建 `.venv`、安装后端和打包依赖、安装 1,097 个前端依赖，`pip check` 无冲突。
- 前端 TypeScript 检查和 Vite 生产构建通过。原前端存在 npm peer dependency、循环 chunk 和动态导入混用警告，未阻断编译，未改动前端业务代码。
- 源码 CLI 帮助和后端 ASGI 应用导入通过。
- PyInstaller 首轮完整构建通过，输出 `dist/paw/paw.exe`；冻结后的 `paw.exe cli --help` 通过。
- 脚本移入 `scripts/` 后，从该目录实际执行 `build-paw.ps1`，前端重新编译、PyInstaller 打包、CLI 检查和发布 ZIP 生成全部通过，确认脚本不依赖调用者的当前目录。
- 最终脚本的 `-SkipFrontend` 构建也实际执行成功，确认配置隔离有效。用临时运行数据验证保护分支：脚本在重建前报错退出，测试文件保持原样；测试文件已清理。
- 发布 ZIP 的 CRC 校验通过，包含前端与内置智能体资源，根目录布局符合启动脚本要求，不含 `.devco_paw` 运行数据。
- 将新生成的 ZIP 解压到 `build/frozen-validation-*` 独立目录，移除 Python / Node 的 PATH 和原有服务配置，仅用占位模型凭据验证。`paw.exe cli --help`、自动生成 `devcopaw.exe` 别名、`paw.exe --init-only` 均通过。原版入口强制启用 default-only，因此首次初始化只创建默认智能体；六个定制智能体 ZIP 资源仍完整保留。
- 解压后的 EXE 在本机回环地址启动成功：`/api/version` 返回 `2.0.0`，首页和全部引用的 JS / CSS 返回 200 且与打包文件内容一致，`/api/agents` 返回默认智能体，后台初始化完成且日志没有异常堆栈。Vite 生成的空 vendor CSS 文件按实际内容校验，不视为资源缺失。
- 初次在沙箱内验证时，Python 事件循环创建回环 socket 被阻塞而超时；诊断堆栈确认后获准在沙箱外重试，通过完整运行检查。该限制不需要修改业务源码。详细检查结果保存在忽略目录 `build/frozen-verification.json`。
- 导入的 756 个 Python 文件语法检查通过；模型环境变量继承、CLI 参数覆盖与无硬编码密钥的默认配置检查通过。
- 1,865 个待提交文本文件及内置 ZIP 的已识别密钥格式扫描通过（安全检测规则中的正则表达式不视为密钥）。
- 复制前后的 1,864 个来源文件 SHA-256 一致。首次整理只调整了五个导入文件，后续版本对齐增加 `.python-version` 这一处目标差异；复制前记录存在忽略目录 `build/source-manifest.json`。
- 共 1,870 个待提交 / 已跟踪文件，导入的必需文件无一被 Git 忽略；环境、构建目录和发布包已忽略。

以上验证覆盖环境安装、前端编译、打包、CLI、首次初始化、本地 Web 服务和资源完整性。实际模型对话、各渠道消息及外部业务工具需要用户自己的服务配置，未执行这些业务集成测试。

## Python 3.11.9 版本对齐验证（完整依赖恢复前）

2026-10-13 按用户要求将当前构建环境对齐为原环境的 **64 位 Python 3.11.9**。原目录未修改，当前 `dist/paw/paw.exe` 与 `dist/paw-runtime.zip` 已由该版本重新生成。

- 两个 PowerShell 脚本语法检查通过。实际验证：初始化和构建脚本均拒绝已有的 3.12.9 环境，`-RecreateVenv -PythonExe <3.12 路径>` 也在备份旧环境前报错退出，旧环境配置保持原样。
- 从 `scripts/` 目录执行 `init-windows.ps1 -RecreateVenv` 成功，旧环境保存至 `build/venv-backups/venv-20261013-102034-400509ad/`，新建 `.venv` 的解释器确认为 3.11.9。后端依赖安装、`pip check` 和前端锁文件安装均通过。
- 从 `scripts/` 目录执行 `build-paw.ps1 -Clean` 成功，重新完成 TypeScript 检查、Vite 生产构建、PyInstaller 打包、冻结 CLI 检查和发布 ZIP 生成。
- 发布目录 `_internal/python311.dll` 的 `FileVersion` 和 `ProductVersion` 均为 `3.11.9`；发布目录和 ZIP 中均无 `python312.dll`。
- 发布 ZIP CRC 检查通过。解压到独立测试目录并从 PATH 移除 Python / Node 后，CLI、自动生成的 `devcopaw.exe` 别名及首次初始化通过。
- 解压后的 EXE 本地 Web 服务通过：版本接口返回 `2.0.0`，首页与引用的 JS / CSS 均返回 200 且内容与打包文件一致，智能体列表包含默认智能体，后台初始化完成且无异常堆栈。测试服务已停止。
- 构建后再次校验：原目录 1,864 个文件 SHA-256 全部一致，当前副本的 756 个 Python 文件在 3.11.9 下语法检查通过。

安装日志：`build/init-python3119.log`；构建日志：`build/build-python3119.log`；发布包运行检查：`build/frozen-verification.json`。这些文件与旧环境备份均已被 Git 忽略。第三方依赖及前端的既有警告仍可能出现，本轮没有修改业务代码来隐藏警告；真实模型、渠道及外部工具的业务集成验证范围仍如上所述。

## 原版依赖完整恢复验证

2026-10-13 按用户要求恢复原目录虚拟环境的全部 Python 包版本。当前环境使用 Python 3.11.9，262 个锁定依赖和当前仓库的 `qwenpaw==2.0.0` 共 263 个包，版本集合与原环境一致。

- 初始化脚本实际重建 `.venv` 并成功执行原版依赖安装、隔离的本地项目安装、`pip check`、完整包版本检查和前端锁文件安装。旧环境已备份到 `build/venv-backups/`。
- `setuptools` 恢复到 65.5.0，`lark-oapi` 恢复到 1.7.2，`fastmcp` / `fastmcp-slim` 恢复到 3.4.6。WebSocket 和企业微信 SDK 保持原版的 15.0.1 和 1.0.2。不再升级运行环境的构建工具或按宽泛约束解析新依赖。
- 环境检查脚本实际验证了版本漂移的失败分支；最终环境中全部 263 个包通过检查，`pip check` 无冲突。本地项目的安装 URL 指向当前仓库，未引用原目录代码。
- `build-paw.ps1 -Clean -SkipFrontend` 构建通过：清理旧缓存后重新生成 EXE，使用源码未变且此前编译验证通过的前端资源。EXE 内置 Python DLL 版本为 3.11.9，冻结 CLI 检查通过。
- 发布包 CRC、独立解压运行、CLI 别名、首次初始化、版本接口、首页及引用的 JS / CSS、智能体列表和后台启动检查全部通过。测试服务已停止，日志无异常堆栈。
- 在开启警告记录的对照检查中，恢复后的 `pkg_resources` 导入和命名空间声明不再发出此前新增的警告；发布包的 CLI、初始化和服务日志中也未出现这组警告。原版已有的 `audioop` / WebSocket 弃用提示不通过屏蔽方式处理。
- 构建后再次校验原目录 1,864 个文件，SHA-256 全部一致；当前源码语法和凭据扫描通过。

安装日志：`build/init-original-deps.log`；构建日志：`build/build-original-deps.log`；最新发布包检查：`build/frozen-verification.json`。提交时需包含新增的 `requirements-windows.lock.txt` 和 `scripts/check-windows-env.py`，运行环境、备份及发布包仍由 Git 忽略。
