# Windows 非 Coding 内置运行时

此功能只作用于 Windows x64、非 Coding、`QWENPAW_FORCE_DIRECT_SUBPROCESS_SYNC=1` 的直接 subprocess 链路。其他场景沿用原有行为。默认总开关关闭。

## 配置接口

- `GET /api/config/bundled-runtimes`：读取配置。
- `PUT /api/config/bundled-runtimes`：修改配置，可只提供需要改变的布尔字段；未提供的字段保持原值。
- `GET /api/config/bundled-runtimes/status`：只读检查随包工具的路径、版本和可用状态，不创建会话环境。

示例：只启用 Python 和 Git。

```json
{"enabled": true, "python": true, "nodejs": false, "git": true}
```

实际使用条件为 `enabled && 对应子开关`。关闭总开关不重置子开关；修改在下一次实际执行的 Chat 请求生效，不删除之前的环境，也不重启正在运行的任务。配置保存在全局 `config.json` 的 `bundled_runtimes` 字段。

## 运行时位置

发布目录默认使用 `paw.exe` 同级的 `runtimes/`。源码运行默认使用仓库根目录的 `runtimes/`。首次可运行：

```powershell
.\.venv\Scripts\python.exe scripts\prepare-bundled-runtimes.py --output runtimes
```

也可以在启动服务前设置 `QWENPAW_BUNDLED_RUNTIMES_DIR` 指向已经准备好的运行时目录。这是服务端环境配置，不接受通过 Chat 请求指定可执行文件。源码目录的 `runtimes/` 已被 Git 忽略。

## 分包发布与安装

`scripts/build-paw.ps1` 会生成两份独立的 ZIP 及各自的 `.sha256` 校验文件：

- `dist/paw-runtime.zip`：根目录只有 `paw.exe` 和 `_internal/`。
- `dist/runtimes.zip`：根目录为 `manifest.json`、`python/`、`node/`、`git/`，没有额外的 `runtimes/` 包装层。

先解压应用包，再创建 `paw.exe` 同级的 `runtimes/` 目录，将工具包解压到该目录。最终应存在 `runtimes/manifest.json`、`runtimes/python/python.exe`、`runtimes/node/node.exe`、`runtimes/git/cmd/git.exe` 等入口。清单、完整工具目录和许可证需要一起保留。未启用内置工具时可以暂不部署工具包；启用后缺少相应文件会使 Chat 初始化报错。

使用 `start-paw.cmd` 默认目录布局时，工具包应解压到 `paw-runtime/runtimes/`。启动脚本不会自动解压 `runtimes.zip`，其 `init` 初始化刷新流程会重建应用目录，之后需要重新部署工具包；也可将工具放在应用目录外，并设置 `QWENPAW_BUNDLED_RUNTIMES_DIR`。部署后可用 `GET /api/config/bundled-runtimes/status` 检查工具状态。

## 每轮 Chat 的处理

1. 在系统提示词构建前读取开关快照，选择第一个可写 `sandbox_mounts`；没有时选择 `<workspace>/session_tmp/<session_id>`。只读挂载不作为安装目标。
2. 只初始化开启项。Python 用内置解释器创建 `.paw-env/python`；Node 使用内置解释器，准备项目 `node_modules`、缺失的最小 `package.json`、`.paw-env/npm-global` 和缓存；Git 只使用随包路径。
3. 有效环境直接复用，不重装第三方库；初始化不下载业务包。跨进程文件锁避免同一工作目录被重复初始化。用户已有 `.venv`、`package.json` 和 `node_modules` 保留。
4. 开启项用托管环境信息替换本地探测结果，并给出符合当前 Shell 语法的安装、执行示例。未开启项保留现有本地探测。Git 开关不改变默认 Shell。
5. 当前请求中的 `execute_shell_command` 在直接 subprocess 分支检查本轮开启的运行时入口。普通命令名补成对应绝对路径；显式路径按实际 `cwd` 解析并检查，不匹配则不执行，返回修正命令让模型重试。只对本条命中的运行时使用其虚拟环境／pip／npm 配置，不向所有 Shell 命令统一注入运行时 PATH，不修改服务端全局 `os.environ`。挂载在下一轮改变时重新选择目录；已有环境不搬迁。

例：工作根为 `D:\demo`、Shell 为 cmd：

```bat
"D:\demo\.paw-env\python\Scripts\python.exe" -m pip install pandas
"D:\demo\.paw-env\python\Scripts\python.exe" task.py
"D:\Paw\runtimes\node\node.exe" "D:\Paw\runtimes\node\node_modules\npm\bin\npm-cli.js" install axios --prefix "D:\demo" --global=false
"D:\Paw\runtimes\node\node.exe" task.js
"D:\Paw\runtimes\git\cmd\git.exe" status
```

每条命令分别调用 `execute_shell_command`，`cwd` 设为当前工作根。PowerShell 示例自动使用 `& '完整路径'`；Bash 示例使用相应引用语法。JS 脚本应位于当前项目内，以便加载项目 `node_modules`。

## Shell 入口检查

检查只作用于已开启项：Python 包括 `python`、对应版本别名、`pip` 和 `py`；Node 包括 `node`、`npm`、`npx`；Git 包括 `git`、`bash`。关闭项和其他程序沿用原逻辑，不探测本地所有环境。

执行顺序为：原子检查 → 专用工具路由检查 → LLM 语义校验 → 内置运行时路径检查／补全 → subprocess。前面的检查已拦截的命令不会进入运行时参数解析。LLM 的 off／warn／block 行为保持原样；路径错误后的模型重试重新经过完整检查链。

- `python task.py` 补成本轮虚拟环境的绝对解释器路径；`pip install pandas` 补成该解释器的 `-m pip install pandas`。
- `node task.js` 补成内置 Node 路径；`npm`／`npx` 补成内置 Node 加对应 CLI 路径。`node <npm-cli.js>` 同时检查 Node 与 CLI 路径。本地 npm 操作缺少目录参数时补充本轮 `--prefix` 和 `--global=false`；显式指定其他目录或全局安装时返回引导。
- `git status` 补成内置 Git 路径，`bash` 使用内置 Bash。
- `./.paw-env/python/Scripts/python.exe task.py` 根据实际 `cwd` 解析；只有与本轮解释器匹配且文件存在才执行。路径比较处理 Windows 大小写、斜杠、`..` 与链接，不使用目录字符串前缀判断。
- `C:\Python312\python.exe task.py`、用户其他 `.venv`、旧挂载环境，以及直接使用基础 `runtimes/python/python.exe` 都返回工具错误、应使用的路径和修正命令；模型重新调用后再检查。不会自动执行被拒绝的命令，不需要用户确认。
- 常见 `cmd /c`、`powershell -Command` 包装中涉及开启项时，引导改用当前默认 Shell 直接调用，避免自动改写多层引号。运行时补全只处理外层入口与约定的 npm 项目参数，不改写内联 Python／JS 代码。

## 错误与边界

启用的运行时缺失、目标目录不可写、托管虚拟环境不完整或基础解释器发生变化时，Chat 返回明确初始化错误，不静默切换到系统版本或其他目录。虚拟环境需要重建时，先移走提示中的 `.paw-env/python` 再重试，避免直接删除已有依赖。

入口检查只识别直接提交的已知运行时调用，保留脚本和文件参数，不递归审查 Python／JS／Shell 脚本内部再次启动的程序，不覆盖所有安装参数或用户代码的文件写入行为。`npm --prefix` 明确指定本地目标；npm 全局 prefix 只负责全局工具。强制禁止所有写入 `runtimes` 需要额外的操作系统权限隔离。
