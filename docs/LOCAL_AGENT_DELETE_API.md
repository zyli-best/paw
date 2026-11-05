# 本地 Agent 删除接口协议

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档版本 | 1.0 |
| 更新日期 | 2026-10-22 |
| 协议状态 | 对应当前实现 |
| HTTP 方法 | `DELETE` |
| 接口路径 | `/api/agents/{agent_id}/local` |
| 响应类型 | `application/json`，UTF-8 |
| 完成方式 | 等待删除完成后返回结果，不返回异步任务 ID |

本文中的 `WORKING_DIR` 指运行服务时确定的工作根目录，以服务实际配置为准。
“本地”指服务端所在机器；客户端远程调用时，删除的仍是服务端本地资源。

## 2. 接口说明与前置条件

接口用于删除一个空闲 Agent：先释放宿主管理的资源和已接入的插件资源，随后删除工作目录、对应治理策略目录及 Agent 注册信息。

调用必须满足以下条件：

1. Agent 已注册，且 ID 不是 `default`。
2. Agent 没有运行中的聊天任务、后台工具调用、ACP 调用或调度任务。
3. Agent 没有尚未结束的相关 HTTP 请求、初始化或旧实例清理。
4. Agent 没有需要先释放的派生 Agent。
5. 工作目录是 `WORKING_DIR/workspaces` 下的独占子目录，不能是该根目录本身。
6. 工作目录不能与其他 Agent 的目录相同、互为父子目录，也不能通过符号链接或 junction 重定向。

已加载但空闲、仅保持 MCP 连接的实例可以删除；接口不会为删除操作主动启动一个未加载的 Agent。

## 3. 请求协议

### 3.1 请求路径

```http
DELETE /api/agents/{agent_id}/local
```

### 3.2 路径参数

| 参数 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `agent_id` | string | 是 | 长度 2～64；仅允许英文字母、数字、连字符、下划线；首尾必须是字母或数字；不能为 `default` |

校验表达式：

```text
^[a-zA-Z0-9][a-zA-Z0-9_-]*[a-zA-Z0-9]$
```

目标以路径参数为准，不需要通过 `X-Agent-Id` 传入。调用方不能通过请求指定待删除的目录。

### 3.3 请求头

| 请求头 | 必填 | 说明 |
| --- | --- | --- |
| `Authorization` | 按部署配置 | 需要身份验证时传入 `Bearer <token>` |
| `Accept` | 否 | 建议为 `application/json` |
| `Content-Type` | 否 | 无请求体，不要求设置 |

接口沿用应用的身份验证策略。启用认证、已有注册用户且请求未被部署配置豁免时，需要有效令牌。

### 3.4 查询参数与请求体

无业务查询参数，无请求体。

接口未定义 `force`、`remove_workspace`、`timeout` 或幂等键。调用方不应依赖额外参数改变删除行为。

### 3.5 请求示例

```http
DELETE /api/agents/research/local HTTP/1.1
Host: 127.0.0.1:8088
Authorization: Bearer <token>
Accept: application/json
```

```bash
curl --request DELETE \
  --header "Authorization: Bearer <token>" \
  --header "Accept: application/json" \
  "http://127.0.0.1:8088/api/agents/research/local"
```

地址和端口使用实际部署值；无需认证的部署可省略 `Authorization`。Windows PowerShell 可使用 `curl.exe` 执行该示例。

## 4. 成功响应

### 4.1 HTTP 状态码

`200 OK`。

### 4.2 响应体

```json
{
  "success": true,
  "agent_id": "research",
  "workspace_removed": true
}
```

| 字段 | 类型 | 必有 | 说明 |
| --- | --- | --- | --- |
| `success` | boolean | 是 | 成功时固定为 `true` |
| `agent_id` | string | 是 | 已删除的 Agent ID |
| `workspace_removed` | boolean | 是 | 工作目录已不存在；原本不存在且其余处理成功时也为 `true` |

成功表示宿主管理的释放操作及已注册的插件清理回调完成，目录处理和注册清理完成。若该 Agent 是当前 Agent，当前选择会恢复为 `default`。

成功响应不包含清理步骤列表。它不表示已卸载全局插件、删除远程 MCP 服务，或撤销第三方平台授权；具体范围见第 8 节。

## 5. 错误响应协议

### 5.1 状态码总览

| HTTP 状态码 | 含义 | 调用方处理 |
| --- | --- | --- |
| `400` | 默认 Agent 不可删除或 ID 不合法 | 修改请求，不直接重复相同请求 |
| `401` | 未认证、令牌无效或已过期 | 获取有效令牌后重试 |
| `404` | Agent 未注册、接口未挂载，或已有资源接口透传不存在错误 | 根据 `detail` 核对接口和 Agent 注册状态 |
| `409` | 运行状态、目录所有权、派生关系或并发操作冲突 | 处理冲突后重试 |
| `503` | 管理器未就绪，或资源释放、目录操作、配置更新发生异常 | 阅读具体原因并处理后再重试 |

既有资源接口抛出的 `HTTPException` 会保留原状态码和 `detail`，因此也可能透传其他错误，例如派生 Agent 释放入口的 `403`。

### 5.2 响应格式 A：字符串错误

用于部分参数错误、身份验证错误、资源不存在，以及管理器未就绪等情况。

```json
{
  "detail": "Agent 不存在"
}
```

### 5.3 响应格式 B：冲突错误

`detail` 是对象，包含 `message`，并按具体原因补充相关标识。

```json
{
  "detail": {
    "message": "Agent 正在运行，请先停止任务再删除",
    "agent_id": "research",
    "running_tasks": ["chat-001"]
  }
}
```

| 字段 | 类型 | 出现条件 |
| --- | --- | --- |
| `message` | string | 冲突错误必有 |
| `agent_id` | string | 部分运行状态和并发冲突 |
| `running_tasks` | string[] | 存在活跃任务 |
| `tool_call_ids` | string[] | 存在未结束的工具调用 |
| `job_id` | string | 存在正在执行的定时任务 |
| `child_agent_ids` | string[] | 存在未释放的派生 Agent |
| `other_agent_id` | string | 工作目录与其他 Agent 重叠 |

这些标识是错误关联资源，不是清理步骤列表。

### 5.4 响应格式 C：详细执行错误

删除前检查、资源释放、目录删除或配置更新中的非 HTTP 异常会转换为 `503`，返回以下格式。

```json
{
  "detail": {
    "message": "删除 Agent 失败，请根据失败原因处理后重试",
    "agent_id": "research",
    "reason": "调用插件资源释放回调失败，涉及资源：remote-plugin（工作目录：D:/qwenpaw/workspaces/research）。系统返回：RuntimeError: connection alive。本次请求尚未执行工作目录删除。建议：检查所示插件或服务的释放接口及对应日志，排除底层错误后重试此接口。",
    "retryable": true
  }
}
```

| 字段 | 类型 | 必有 | 说明 |
| --- | --- | --- | --- |
| `detail.message` | string | 是 | 删除失败的通用提示 |
| `detail.agent_id` | string | 是 | 目标 Agent ID |
| `detail.reason` | string | 是 | 失败操作、涉及资源、底层错误、删除状态及处理建议 |
| `detail.retryable` | boolean | 是 | 当前实现固定为 `true`，表示可在排除原因后重新尝试，不代表立即重试必然成功 |

`reason` 会按实际错误提供以下信息：

- 失败的具体操作及资源，如插件回调名、MCP 客户端名、ACP 会话、工作目录或配置文件。
- 异常类型和原始错误信息。
- 异常提供的 `errno`、`winerror`、`filename`、`filename2`。
- 包装异常的底层原因，以及异常组包含的子异常。
- 本次是否尚未执行目录删除、是否可能部分删除，或是否在目录完成删除后配置更新失败。
- 根据权限、文件占用、超时、磁盘空间或连接错误给出的处理建议。

不返回 `cleanup_steps`、`completed_steps`、`failed_stage` 或宿主生成的调用栈。
当前没有独立的机器错误码字段；`reason` 是诊断文本，客户端应展示它，不应依赖对其文字进行解析来驱动业务状态。

`503` 的管理器未就绪错误仍使用格式 A；透传的 `HTTPException` 也不保证使用格式 C。

## 6. 详细错误目录

### 6.1 请求和认证错误

| HTTP 状态码 | 实际错误或条件 | 说明与处理 |
| --- | --- | --- |
| `400` | `不能删除默认 Agent` | `default` 受保护 |
| `400` | ID 长度小于 2 或大于 64 | 校验提示包含实际长度，当前提示为英文 |
| `400` | ID 包含非法字符，或以 `-`、`_` 开头/结尾 | 使用符合第 3.2 节规则的 ID |
| `401` | `Not authenticated` | 需要认证但未提交令牌 |
| `401` | `Invalid or expired token` | 令牌无效或过期 |
| `404` | `Agent 不存在` | 注册配置中没有目标 Agent |
| `404` | `Not Found` | URL 不匹配、可选模块未加载等路由问题 |
| `503` | `Agent manager is not ready` | 管理器尚未就绪，等待服务初始化 |

### 6.2 运行状态和并发冲突

以下均为 `409`，通常使用格式 B。

| `detail.message` | 附加字段 | 处理方式 |
| --- | --- | --- |
| `Agent 正在启动，请稍后重试` | `agent_id` | 等待初始化结束 |
| `Agent 的旧实例尚未退出，请稍后重试` | `agent_id` | 等待旧实例退出 |
| `Agent 尚有请求未结束，请稍后重试` | `agent_id` | 等待相关请求结束 |
| `Agent 正在运行，请先停止任务再删除` | `agent_id`、`running_tasks` | 停止列出的任务或等待完成 |
| `Agent 有未结束的工具调用` | `tool_call_ids` | 结束对应工具调用 |
| `Agent 有未结束的外部 ACP 调用` | `agent_id` | 结束外部 ACP 执行 |
| `Agent 有正在执行的调度任务` | `agent_id` | 等待或停止调度任务 |
| `Agent 有正在执行的定时任务` | `job_id` | 结束对应定时任务 |
| `Agent 正在删除，请勿重复操作` | `agent_id` | 等待已有删除请求完成 |
| `请先释放派生 Agent 再删除父 Agent` | `child_agent_ids` | 先释放列出的派生 Agent |

删除期间，针对该 Agent 的其他已识别的 HTTP 请求会被删除保护拦截，可能收到格式 A 的 `409`：`{"detail":"Agent 正在删除"}`。

### 6.3 目录和所有权冲突

以下均为 `409`，使用格式 B。

| `detail.message` | 条件或处理方式 |
| --- | --- |
| `只能删除 workspaces 下独占且未重定向的本地工作目录` | 路径不在受管理范围、指向根目录或发生重定向；核对 Agent 的工作目录配置 |
| `工作目录路径包含符号链接或 junction，不能自动删除` | 不能由此接口自动删除链接路径 |
| `工作目录与其他 Agent 重叠` | 根据 `other_agent_id` 处理相同目录或父子目录关系 |
| `Agent 工作目录不是目录` | 目标路径是文件等非目录对象 |
| `Agent 工作目录已改变，请重新发起删除` | 删除前复核发现路径改变 |
| `Agent 的治理目录发生重定向，不能自动删除` | 治理策略目录的解析结果不符合预期 |
| `上次清理后工作目录已改变，不能自动重试` | 进程内保留的失败上下文与当前配置不一致，需先核对配置及已有资源 |

### 6.4 资源和存储错误

以下非 HTTP 异常使用 `503` 和格式 C。具体异常名、路径、资源名以实际响应为准。

| 错误类别 | 原因 | `reason` 中提供的处理方向 |
| --- | --- | --- |
| Windows 文件占用 | `winerror=32` 或 `33` | 关闭占用文件的程序并等待句柄释放 |
| 权限不足 | `PermissionError` | 核对访问权限、只读属性及程序占用；不把所有权限错误都认定为文件占用 |
| 释放超时 | `TimeoutError` | 检查对应服务是否响应、插件回调是否阻塞 |
| 磁盘空间不足 | `errno=ENOSPC` | 检查配置所在磁盘的剩余空间 |
| 连接异常 | `ConnectionError` 及其子类 | 检查所示服务连接和远端状态 |
| 插件回调异常 | 回调抛出异常或无法结束 | 显示回调或插件名称及底层错误，修复后重试 |
| MCP 关闭异常 | 客户端无法关闭，或底层释放方法报告异常 | 显示 MCP 客户端名称及底层错误 |
| MCP 配置/凭据异常 | 配置读取、解析、凭据删除失败 | 核对所示资源、对应文件和错误信息 |
| ACP、浏览器、LSP、渠道等异常 | 对应释放方法报错 | 核对具体服务、会话或项目路径 |
| 目录删除异常 | 工作目录或治理目录无法删除 | 显示相关目录，以及系统错误提供的具体文件路径 |
| 注册/配置更新异常 | 删除注册或恢复当前 Agent 选择时无法保存配置 | 核对 `config.json`；目录可能已经删除 |

既有释放方法若只记录错误而不抛异常，本模块会捕获受监控方法的警告/错误日志并将其视为删除失败。日志包含底层异常时，响应也会附带底层原因。

## 7. 典型响应示例

### 7.1 Agent 正在运行

HTTP `409`：

```json
{
  "detail": {
    "message": "Agent 正在运行，请先停止任务再删除",
    "agent_id": "research",
    "running_tasks": ["chat-001", "ext-002"]
  }
}
```

### 7.2 尚有派生 Agent

HTTP `409`：

```json
{
  "detail": {
    "message": "请先释放派生 Agent 再删除父 Agent",
    "child_agent_ids": ["system_agent_0123456789abcdef"]
  }
}
```

### 7.3 MCP 连接关闭失败

HTTP `503`：

```json
{
  "detail": {
    "message": "删除 Agent 失败，请根据失败原因处理后重试",
    "agent_id": "research",
    "reason": "关闭 MCP 客户端连接失败，涉及资源：客户端 search（工作目录：D:/qwenpaw/workspaces/research）。系统返回：ConnectionResetError: peer closed the connection。本次请求尚未执行工作目录删除。建议：检查所示服务连接和远端状态，确认连接可正常关闭后重试。",
    "retryable": true
  }
}
```

### 7.4 插件回调超时

HTTP `503`：

```json
{
  "detail": {
    "message": "删除 Agent 失败，请根据失败原因处理后重试",
    "agent_id": "research",
    "reason": "调用插件资源释放回调失败，涉及资源：remote-plugin（工作目录：D:/qwenpaw/workspaces/research）。系统返回：TimeoutError: 操作未在 30 秒内完成。本次请求尚未执行工作目录删除。建议：检查对应服务是否响应、插件释放回调是否阻塞，确认资源可释放后重试。",
    "retryable": true
  }
}
```

### 7.5 工作目录删除失败

HTTP `503`：

```json
{
  "detail": {
    "message": "删除 Agent 失败，请根据失败原因处理后重试",
    "agent_id": "research",
    "reason": "删除 Agent 工作目录失败，涉及资源：D:/qwenpaw/workspaces/research。系统返回：PermissionError: file is being used（errno=13；winerror=32；filename=D:/qwenpaw/workspaces/research/sessions/chat.json）。目录删除未完成，部分文件可能已经删除；Agent 注册清理尚未执行。建议：关闭占用所示文件的程序，确认相关进程已释放句柄后重试。",
    "retryable": true
  }
}
```

### 7.6 目录已删除，但配置保存失败

HTTP `503`：

```json
{
  "detail": {
    "message": "删除 Agent 失败，请根据失败原因处理后重试",
    "agent_id": "research",
    "reason": "更新当前 Agent 配置失败，涉及资源：D:/qwenpaw/config.json。系统返回：PermissionError: configuration is read-only。工作目录删除操作已完成，但 Agent 注册或当前 Agent 配置未全部更新成功。建议：检查所示文件或目录的访问权限、只读属性及程序占用情况，解除限制后重试。",
    "retryable": true
  }
}
```

示例中的路径、资源名和系统错误用于说明格式，实际响应可能包含操作系统生成的额外文件信息。

## 8. 资源释放和删除范围

| 资源 | 处理方式 | 范围 |
| --- | --- | --- |
| ACP | 复用 `close_all_sessions()`，等待完成后调用 `close_acp_service(agent_id)` | 当前 Agent 的外部 ACP 会话及服务注册 |
| MCP | 复用 `handler.shutdown()`、`MCPConfigService.delete_client()`、`shutdown_all()` | 当前 Agent 的连接、客户端配置及关联本地凭据 |
| 浏览器 | 复用 `stop_browsers_for_workspace_dirs([path])` | 当前工作目录的宿主管理浏览器 |
| LSP | 调用对应客户端的 `shutdown()` | 项目根目录位于待删工作目录内的池化客户端 |
| 插件 | 调用插件 `cleanup_agent()` 或已注册的清理回调 | 回调显式负责的该 Agent 资源 |
| 调度、渠道、监听及工作区服务 | 复用对应停止方法和工作区服务停止流程 | 当前 Agent 的宿主管理服务 |
| 审批和本地索引 | 调用审批处理方法，清理当前 Agent 的相关索引 | 当前 Agent 的关联状态 |
| 工作目录 | 删除目录及其中内容 | 包括位于其中的会话、记忆、配置、凭据及文件 |
| 治理策略目录 | 删除对应工作区的策略目录 | `WORKING_DIR/governance` 下对应条目 |
| Agent 注册信息 | 复用已有删除入口，更新当前 Agent 配置 | 当前 Agent 的注册和顺序；必要时恢复选择到 `default` |

这些调用是 Python 服务层方法，不是向本应用发起内部 HTTP 请求。
部分资源枚举和失败重试使用现有内部索引，因此不能将当前实现视为完全只依赖公开接口。

全局插件本体、共享模型配置、远程 MCP 服务、远程业务数据和第三方授权不属于自动删除范围。
位于工作目录外的其他项目文件不随工作目录删除。

插件没有实现或注册清理回调时，当前接口会跳过其自定义资源清理，不会仅因此报错。
因此，`200` 不保证未纳入宿主管理、也未注册回调的插件外部资源已经释放。

## 9. 失败状态、重试和超时

### 9.1 数据状态

| 失败位置 | 当前实现的状态 |
| --- | --- |
| 初始校验或运行状态检查 | 尚未执行资源停止或目录删除 |
| 禁用配置保存失败 | 尚未执行目录删除，配置写入结果需结合错误核对 |
| 禁用成功后的资源释放失败 | Agent 通常保持禁用；本次尚未执行目录删除，但可能已有资源关闭或配置被清理 |
| 消息入口停止后的二次运行检查冲突 | 可返回 `409`；目录尚未删除，但 Agent 可能已禁用、部分入口已停止 |
| 删除治理目录或工作目录失败 | 部分文件可能已经删除；注册清理尚未执行 |
| 最后的注册或当前 Agent 配置更新失败 | 目录操作已完成，注册可能保留，也可能已移除但当前 Agent 选择未保存成功 |

本接口不提供事务回滚。不能根据非 `200` 响应推断“所有数据保持原样”，也不能根据所有 `409` 都推断“没有发生资源停止”。

### 9.2 重试约定

1. 同一个 Agent 的删除尚在执行时，重复请求返回 `409`。
2. 处理 `503` 的具体原因后，可以再次请求；成功的清理回调也可能再次执行，所以回调必须支持重复调用。
3. 成功删除后再次请求，通常返回 `404`，不是再次返回 `200`。接口不提供基于幂等键的结果回放。
4. 注册已部分移除、响应又失败时，先通过 `GET /api/agents` 核对当前注册，再决定是否重试或修复配置。
5. 原有资源接口透传的 `404` 不一定表示 Agent 已经删除，应结合 `detail` 和注册查询确认。
6. 当前失败上下文和删除任务保存在服务进程内；没有持久化删除任务或跨重启的自动续跑协议。

`retryable: true` 不是立即自动重试指令，也不是状态已回滚的声明。当前接口不返回 `Retry-After`。

### 9.3 超时和客户端断开

资源释放分组使用默认 30 秒超时。该值不是整个 HTTP 请求的总超时，也不能据此将客户端总超时固定为 30 秒。

同步回调运行于工作线程，取消时会等待其结束以避免资源释放与后续删除竞争，因此实际等待可能超过该值。
目录操作和配置写入也没有统一的 HTTP 总超时保证。

客户端连接断开或请求超时，不表示已取消服务端删除。当前进程中的删除任务可能继续完成。
调用方应先核对 Agent 注册及原请求状态，避免立即并发重试；本接口不提供任务状态查询 ID 或取消接口。

## 10. 插件清理回调约定

以下是 Python 扩展约定，不是额外的 HTTP 接口。

### 10.1 插件实例方法

```python
async def cleanup_agent(*, agent_id: str, workspace_dir: Path) -> None:
    ...
```

插件实例存在可调用的 `cleanup_agent` 时会被调用。同步方法也受支持。

### 10.2 注册命名回调

```python
from qwenpaw.app.routers.local_agent_delete import (
    register_agent_cleanup,
    unregister_agent_cleanup,
)

register_agent_cleanup("my-plugin", cleanup_agent)

# 插件卸载时解除注册。
unregister_agent_cleanup("my-plugin")
```

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `agent_id` | string | 当前被删除的 Agent |
| `workspace_dir` | `pathlib.Path` | 待删除的工作目录 |

回调必须满足：

- 只释放目标 Agent 拥有的连接、进程、任务和外部资源。
- 返回前等待资源释放完成；无法确认释放成功时抛出异常。
- 支持重复执行；资源已经不存在时应按已释放处理。
- 不卸载其他 Agent 共享的全局插件。

返回值不会用于判断是否成功；仅返回 `False` 不会被视为失败，必须抛出异常。
注册同名回调会替换旧回调。不要同时以实例方法和不同命名回调注册同一份非幂等释放逻辑。

## 11. 客户端响应处理建议

1. 使用 HTTP 状态码区分成功、请求问题、冲突和执行失败。
2. 对 `200` 读取成功响应字段。
3. 错误时，若 `detail` 是字符串，直接展示它。
4. 若 `detail` 是对象，优先展示 `reason`，不存在时展示 `message`。
5. 可以用 `running_tasks`、`tool_call_ids`、`job_id`、`child_agent_ids`、`other_agent_id` 定位冲突对象。
6. 不期待清理步骤字段，不将 `reason` 文本作为稳定的机器错误码。

## 12. 实现对应

- 删除接口与失败原因格式：`src/qwenpaw/app/routers/local_agent_delete.py`。
- 可选加载入口：`src/qwenpaw/app/_app.py`。
- 回归测试：`tests/test_local_agent_delete.py`。

本协议描述新增的 `/api/agents/{agent_id}/local`，不表示旧删除接口或 CLI 已切换为该流程。
