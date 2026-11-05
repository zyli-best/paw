# 内置 Python、Node.js、Git 接口调用文档

## 1. 请求约定

示例服务地址为 `http://127.0.0.1:8088`，请按实际地址和端口修改。

- JSON 请求使用 `Content-Type: application/json`。
- 需要认证时，携带 `Authorization: Bearer <token>`。
- 配置接口控制全局开关；执行任务通过聊天接口提交。

PowerShell 示例复用以下变量：

```powershell
$baseUrl = 'http://127.0.0.1:8088'
$headers = @{}

# 需要认证时设置已获取的 Token。
# $token = 'YOUR_TOKEN'
# $headers = @{ Authorization = "Bearer $token" }
```

| 方法 | 地址 | 用途 |
| --- | --- | --- |
| GET | `/api/config/bundled-runtimes` | 查询开关 |
| PUT | `/api/config/bundled-runtimes` | 修改开关 |
| GET | `/api/config/bundled-runtimes/status` | 查询工具可用状态 |
| POST | `/api/console/chat` | 提交使用 Python、Node.js、Git 的任务 |

## 2. 查询开关

**请求**

```http
GET /api/config/bundled-runtimes
```

```powershell
Invoke-RestMethod -Method Get `
    -Uri "$baseUrl/api/config/bundled-runtimes" -Headers $headers
```

**响应示例：HTTP 200**

```json
{
  "enabled": false,
  "python": true,
  "nodejs": true,
  "git": true
}
```

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | boolean | `false` | 总开关 |
| `python` | boolean | `true` | Python 子开关 |
| `nodejs` | boolean | `true` | Node.js 子开关 |
| `git` | boolean | `true` | Git 子开关 |

使用某项工具时，总开关和对应子开关均需为 `true`。

## 3. 修改开关

**请求**

```http
PUT /api/config/bundled-runtimes
Content-Type: application/json
```

四个字段均可选，只修改请求中提供的字段。字段值必须是 JSON 布尔值。

### 3.1 全部开启

请求体：

```json
{
  "enabled": true,
  "python": true,
  "nodejs": true,
  "git": true
}
```

PowerShell 调用：

```powershell
$body = @{
    enabled = $true
    python = $true
    nodejs = $true
    git = $true
} | ConvertTo-Json

Invoke-RestMethod -Method Put `
    -Uri "$baseUrl/api/config/bundled-runtimes" `
    -Headers $headers -ContentType 'application/json' -Body $body
```

响应示例：HTTP 200，返回修改后的完整配置。

```json
{
  "enabled": true,
  "python": true,
  "nodejs": true,
  "git": true
}
```

### 3.2 只关闭 Node.js

使用相同 PUT 地址，请求体：

```json
{
  "nodejs": false
}
```

其他字段保留原值。

### 3.3 关闭总开关

使用相同 PUT 地址，请求体：

```json
{
  "enabled": false
}
```

子开关保留原值。修改在下一次新任务中生效，已运行的任务继续执行。

## 4. 查询工具状态

**请求**

```http
GET /api/config/bundled-runtimes/status
```

```powershell
Invoke-RestMethod -Method Get `
    -Uri "$baseUrl/api/config/bundled-runtimes/status" `
    -Headers $headers | ConvertTo-Json -Depth 6
```

**响应示例：HTTP 200**

路径和版本按实际部署返回。

```json
{
  "directory": "D:\\Paw\\runtimes",
  "supported_platform": true,
  "runtimes": {
    "python": {
      "available": true,
      "version": "3.11.18",
      "error": "",
      "executable": "D:\\Paw\\runtimes\\python\\python.exe"
    },
    "nodejs": {
      "available": true,
      "version": "22.23.4",
      "error": "",
      "executable": "D:\\Paw\\runtimes\\node\\node.exe",
      "npm_cli": "D:\\Paw\\runtimes\\node\\node_modules\\npm\\bin\\npm-cli.js",
      "npx_cli": "D:\\Paw\\runtimes\\node\\node_modules\\npm\\bin\\npx-cli.js"
    },
    "git": {
      "available": true,
      "version": "2.56.0.windows.4",
      "error": "",
      "executable": "D:\\Paw\\runtimes\\git\\cmd\\git.exe",
      "bash": "D:\\Paw\\runtimes\\git\\bin\\bash.exe"
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `directory` | 工具包根目录 |
| `supported_platform` | 当前平台是否受支持 |
| `runtimes` | 各工具的状态 |
| `available` | 工具是否通过可用性检查 |
| `version` | 工具版本 |
| `error` | 不可用原因；正常时为空字符串 |
| `executable` | 工具程序路径；Python 此处为基础解释器路径 |
| `npm_cli` / `npx_cli` | npm / npx 入口路径 |
| `bash` | Git Bash 路径 |

工具不可用时，接口仍可能返回 HTTP 200，请检查对应的 `available` 和 `error`。

## 5. 通过聊天接口提交任务

使用前开启所需工具，并使用普通非 Coding 模式。以下示例假设服务端已存在 `D:\demo` 目录。

**请求**

```http
POST /api/console/chat
Content-Type: application/json
```

请求体，保存为 UTF-8 文件 `chat-request.json`：

```json
{
  "session_id": "bundled-runtime-demo",
  "user_id": "demo-user",
  "channel": "console",
  "input": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "请在 D:/demo 中分别执行 python --version、node --version、git --version，并报告结果。每条命令单独调用 execute_shell_command，cwd 使用 D:/demo。"
        }
      ]
    }
  ],
  "request_context": {
    "sandbox_mounts": ["D:/demo"]
  }
}
```

| 字段 | 示例值 | 说明 |
| --- | --- | --- |
| `session_id` | `bundled-runtime-demo` | 会话标识，同一会话后续请求复用该值 |
| `user_id` | `demo-user` | 用户标识 |
| `channel` | `console` | 使用控制台聊天通道 |
| `input` | 见示例 | 用户消息 |
| `request_context.sandbox_mounts` | `["D:/demo"]` | 服务端已存在的工作目录列表，示例使用一个目录 |

PowerShell 中调用，无需认证时：

```powershell
curl.exe -N "$baseUrl/api/console/chat" `
    -H 'Content-Type: application/json' `
    --data-binary '@chat-request.json'
```

需要认证时：

```powershell
curl.exe -N "$baseUrl/api/console/chat" `
    -H 'Content-Type: application/json' `
    -H "Authorization: Bearer $token" `
    --data-binary '@chat-request.json'
```

响应为 SSE（`Content-Type: text/event-stream`），通过流中的工具结果和回复读取执行结果。HTTP 200 表示聊天请求已接收，具体命令是否成功以执行结果为准。

替换消息的 `text` 即可提交其他任务，例如：

| 场景 | 消息示例 |
| --- | --- |
| Python | `请在 D:/demo 安装 requirements.txt 中的依赖，再执行 task.py。` |
| Node.js | `请在 D:/demo 安装 axios，再执行 task.js。` |
| Git | `请查看 D:/demo 仓库的 git status。` |

## 6. 工具调用参数与示例

以下为 Agent 调用 `execute_shell_command` 时的参数，供集成方组织任务和查看工具调用时参考。它们不是 HTTP 接口请求体。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `command` | string | 是 | 要执行的命令 |
| `cwd` | string | 否 | 执行目录，建议显式传入 |
| `timeout` | number | 否 | 超时秒数，未指定时使用 Agent 默认设置，通常为 60 秒 |

### 6.1 Python 安装依赖

```json
{
  "command": "python -m pip install opencv-python-headless numpy",
  "cwd": "D:\\demo",
  "timeout": 600
}
```

### 6.2 Python 执行脚本

假设 `D:\demo\task.py` 已存在：

```json
{
  "command": "python task.py",
  "cwd": "D:\\demo",
  "timeout": 300
}
```

### 6.3 Node.js 安装依赖

```json
{
  "command": "npm install axios --prefix D:/demo --global=false",
  "cwd": "D:\\demo",
  "timeout": 600
}
```

### 6.4 Node.js 执行脚本

假设 `D:\demo\task.js` 已存在：

```json
{
  "command": "node task.js",
  "cwd": "D:\\demo",
  "timeout": 300
}
```

### 6.5 Git 查询版本

```json
{
  "command": "git --version",
  "cwd": "D:\\demo",
  "timeout": 60
}
```

### 6.6 Git 查看仓库状态

假设 `D:\demo` 已是 Git 仓库：

```json
{
  "command": "git status",
  "cwd": "D:\\demo",
  "timeout": 60
}
```

每个 JSON 示例分别作为一次工具调用。依赖安装成功后，再执行对应脚本。

## 7. 常见错误响应

| 情况 | 响应或结果 |
| --- | --- |
| 配置查询或修改成功 | HTTP 200，返回配置对象 |
| 缺少认证或 Token 无效 | HTTP 401 |
| 开关传入字符串、数字、null 或额外字段 | HTTP 422 |
| 聊天请求中的工作目录无效 | HTTP 400 |
| 工具不可用 | 状态响应中 `available=false`，查看 `error` |
| 命令执行失败 | 工具输出中包含 `Command failed with exit code ...` |
| 命令执行超时 | 工具输出中包含 `Command execution exceeded the timeout of ... seconds.` |

错误请求示例：

```json
{
  "enabled": "true"
}
```

应改为：

```json
{
  "enabled": true
}
```
