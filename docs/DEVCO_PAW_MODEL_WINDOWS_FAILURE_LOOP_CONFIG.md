# DevCo Paw：单文件模型协议、Windows Shell 与 FailureLoopGate 方案

核对日期：2026-10-15。已在源码中实现自动路由及参数适配，业务改动涉及两个 Provider 文件，以及 FailureLoopGate 的 ToolChoice 导入和调用参数；未修改部署配置，未调用私有网关，未复制凭据。

项目模型只使用现有 `providers/custom/fw-agent-project.json`，所有项目模型引用继续使用 `provider_id: fw-agent-project`。不增加其他项目提供商文件，不新增 api_type 等协议配置字段。部署根目录为 `D:\work_tools\devco\DevCo\third\devco_paw\paw-runtime`。

## 1. 已确认的现状

- 项目提供商顶层为 `chat_model: OpenAIChatModel`，模型条目在 `extra_models`，`models` 为空。
- Sol 的 `generate_kwargs.reasoning_effort` 为 high，携带工具时发生 HTTP 400；Luna 未显式设置 effort。
- 全局 active_model 是 Luna，default Agent 单独选择 Sol，PCR Agent 单独选择 Qwen3.8-max-0902。
- default、PCR 的配置均为非 Coding，Shell executable 为空；没有 SHELL 环境覆盖时 Windows 回退到 cmd.exe。
- 日志显示 FailureLoopGate 为 disabled_by_config；Qwen Shell 审查已有 enable_thinking=false 的运行记录。

ProviderManager 根据文件顶层 chat_model 创建具体 Provider，再按 Agent 的 provider_id 查找它。修改前自定义 Qwen 有专门的 DashScope 路由，GPT 没有自动 Responses 路由；本次在同一构造入口补充了已确认 GPT 的路由，不新增模型级协议字段。

## 2. 旧运行包未更新时的临时配置

保持 fw-agent-project.json 的顶层 chat_model 为 OpenAIChatModel，分别把 Sol、Luna 模型条目的 generate_kwargs 改为：

```json
{
  "reasoning_effort": "none"
}
```

这是模型条目的生成参数片段，其他字段继续保留。不要在提供商顶层统一设置，以免影响 Qwen、DeepSeek 等模型。所有 active_model 的 provider_id 保持 fw-agent-project。

此方案用于旧运行包，恢复其 GPT Chat 工具兼容性，但主任务及 FailureLoopGate 的 GPT 推理都会关闭。更新为本次源码后，已确认的在线自定义 GPT 无论 effort 是否为 none 均自动使用 Responses；none 只控制推理开关。

## 3. 已实现：单文件、无新增字段、代码自动选择协议

在自定义 OpenAI 提供商的模型构造入口新增统一的模型协议规则。配置结构、Provider ID、凭据、base_url、原模型参数均可保留；前端和模型配置 API 不需要新增字段。本地提供商（is_local=true 或 id=fw-agent-local）沿用原路由。

先覆盖当前实际使用且协议限制已确认的 gpt-5.6-sol、gpt-5.6-luna。其他已确认模型可逐项加入代码中的能力表。仅使用实际请求 model_id 匹配，不根据界面显示名、IP 地址或模糊的 gpt-* 前缀推断。未知模型沿用现有路径，不将所有未来 GPT 或专用变体自动套入同一策略。

```text
fw-agent-project.json（现有结构）
  → OpenAIProvider(id=fw-agent-project)
  → get_chat_model_instance(model_id)
      → 已确认的 GPT：Responses 模型 + Responses Formatter
      → Qwen：现有 DashScope 路径
      → DeepSeek / 其他模型：现有默认路径
```

路由在构造模型时确定，后续不因请求是否带 tools、effort 是否为 none 而切换协议。因此主任务、独立创建的 Shell guard、复用主模型的 FailureLoopGate 会选择同一协议。

Responses 分支复用现有 OpenAIResponseProvider 构造逻辑，可使用同 id、同凭据、同 base_url 的临时内存对象，也可抽取共同构造函数。不注册新提供商，不保存额外文件，不改写共享 Provider 或模型配置。

Sol 原有参数可以继续保留：

```json
{
  "reasoning_effort": "high"
}
```

适配层将其转换为 Responses 的 reasoning.effort=high，并移除旧顶层键。Luna 未指定 effort 时继续省略，交由服务端默认处理。显式 none 必须被保留；不能用真假值判断误丢弃。若新旧格式并存，建议仅旧格式存在时转换，两者值相同则归一，冲突时给出明确配置错误，不静默选择。

归一化应基于独立副本，处理合并后的提供商/模型参数，以及单次调用覆盖；Shell 明确发送的 none 必须覆盖继承的 high。max_tokens 继续按现有 Responses 构造逻辑变为 max_output_tokens，消息、工具 schema、返回事件都使用对应 Formatter 和解析器。网关 base_url 的项目路径前缀完整保留，由 SDK 拼接接口路径，不自行替换为其他主机或硬编码 /v1。

本次实现范围：

1. 新增代码内部的协议选择函数和两个已确认模型的集合，供实例构造与连接检查共用。
2. OpenAIProvider.get_chat_model_instance 增加 GPT Responses 分支，保留 Qwen 及其他模型原路径。OpenAIResponseProvider 已显式选用 Responses 时直接构造，避免互相路由造成递归。
3. Responses 适配层增加旧推理参数的归一化，保证单次调用覆盖优先，并且不污染共享配置。
4. 模型连通性检查使用实际路由。媒体探测如果仍使用 Chat，应说明其检查范围。
5. 路由日志记录 Responses 适配器及原 provider_id，不记录凭据。FailureLoopGate 直接传入当前 AgentScope 的 ToolChoice(mode=none)，兼容 GPT、Qwen 等所有现有适配器。

私有网关支持 Responses 是必要条件，尚未验证。若不支持，应返回清晰错误并保留请求的 high 意图；不要静默退回 Chat、关闭推理、重复执行整个任务。上线前用同一网关验证完整工具往返。网关暂不能支持时，当前版本可先使用第 2 节纯配置方案。

## 4. Windows Shell 配置

在 default、PCR 各自 agent.json 的 running 中合并：

```json
{
  "shell_command_executable": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
  "shell_command_timeout": 60.0
}
```

该 Windows PowerShell 路径已确认存在。也可使用受维护的独立 PowerShell 7 安装路径，避免依赖 Codex 私有运行时。

给实际启动 Paw 的进程配置：

```powershell
$env:QWENPAW_FORCE_DIRECT_SUBPROCESS_SYNC = '1'
$env:QWENPAW_WINDOWS_DIRECT_SHELL_GUARD = 'block'
$env:QWENPAW_WINDOWS_DIRECT_SHELL_LLM_GUARD = 'block'
$env:QWENPAW_WINDOWS_DIRECT_SHELL_LLM_GUARD_OUTPUT = 'auto'
$env:QWENPAW_SHELL_GUARD_DISABLE_THINKING = '1'
$env:QWENPAW_SHELL_GUARD_THINKING_PARAM = 'auto'
$env:QWENPAW_SHELL_GUARD_TOKEN_LIMIT_PARAM = 'auto'
$env:QWENPAW_WINDOWS_DIRECT_SHELL_LLM_GUARD_MAX_TOKENS = '2048'
```

2048 是审查输出预算建议起点，截断时需增加；不会更改主模型预算。auto 按实际模型区分协议，不能全局强制同一种 thinking 参数。

Shell guard 使用当前 Agent 的模型工厂新建独立实例。自动协议选择在 Provider 构造入口完成，保证主任务和 Shell 协议一致。guard 已支持识别 Responses 模型：GPT Responses 审查发送 reasoning.effort=none；GPT Chat 审查发送 reasoning_effort=none；Qwen 审查发送 enable_thinking=false。本地提供商和三个指定本地模型保留原 thinking 策略。

主入口的语义审查超时当前为 180 秒，与命令执行的 60 秒超时不同。Windows 非 Coding 模式一次一个原子操作的规则继续生效。

## 5. FailureLoopGate 配置和效果

给启动进程增加：

```powershell
$env:QWENPAW_FAILURE_LOOP_ENABLED = '1'
$env:QWENPAW_FAILURE_LOOP_CHECK_INTERVAL = '5'
$env:QWENPAW_FAILURE_LOOP_MAX_HINT_TOKENS = '512'
```

也可在现有 Paw 启动命令追加：

```text
--shell-guard-disable-thinking 1 --failure-loop-enabled 1 --failure-loop-check-interval 5 --failure-loop-max-hint-tokens 512
```

显式 CLI 参数优先于环境变量。如果 DevCo 传 enabled=0，要修改启动方参数。上述字段属于启动环境，放入 provider JSON 不会启用检查器；不能假设任意新建 .env 会自动加载。

| 调用链 | 当前纯配置方案 | 实现自动协议选择后的目标 |
| --- | --- | --- |
| GPT 主任务 | Chat，none | Responses，Sol high / Luna medium |
| GPT Shell 审查 | Chat，显式 none | Responses，显式 none |
| GPT FailureLoopGate | 复用主模型，none | 复用主模型及其 Responses 和 effort |
| Qwen 主任务、复查 | 原有适配器与参数 | 原有适配器与参数 |
| Qwen Shell 审查 | enable_thinking=false | enable_thinking=false |

FailureLoopGate 直接复用主模型对象，以 tools=[]、tool_choice=none 检查；没有独立的 review-model、review-effort 或 review-max-tokens 配置。Shell 的推理开关不修改主模型或 FailureLoopGate。

检查器仅在 Windows、本次请求有效模式为非 Coding 时装配。5 统计完成的工具轮；512 只限制下一次主推理的引导长度，不是复查模型输出预算。历史记录在相应工作区 failure_loop/history.db。

## 6. 应用与验收

- 部署时需更新运行包以包含上述源码改动；本次未打包或替换现有 exe。旧包可先使用第 2 节临时配置。
- Agent 和全局模型引用继续使用 fw-agent-project，无需迁移 provider_id。
- 将环境和参数传给实际创建 Paw 子进程的启动方，重启后生效；其他终端设置变量不影响已运行的 DevCo。
- 用允许的无副作用只读命令验证 Shell，保持 guard 开启。日志检查实际 api、model、thinking_mode、token_field。
- 新 Windows 非 Coding 请求应出现 FailureLoopGate enabled=True reason=enabled interval=5。自然达到 5 个工具轮时应出现 review due 和 model review，不额外执行凑轮数操作。
- GPT 完成一组工具调用、工具结果、继续回答；同文件的 Qwen 等模型保持原行为。普通 ping 不能代替该验证。
- 原配置无需补字段，重启、切换模型后仍按统一规则路由，且不会产生新项目提供商文件。
- 离线检查 SDK 边界：Sol 的 high 转换正确，Shell 的 none 覆盖正确，Qwen/DeepSeek 保持原路径，Provider 配置对象未被改写。再以真实网关验证工具往返和流式响应。

本次离线回归已通过 155 项，覆盖新路由、参数缺省/覆盖、Shell thinking 开关，以及真实 FailureLoopGate 使用 GPT、Qwen、DeepSeek 保留 thinking 的请求。接口均使用模拟客户端；私有网关和部署 exe 未联调或替换。

DevCo seed 默认生成 Chat 配置。本方案的自动路由不依赖新增字段，但强制初始化/模型同步仍可能重置现有生成参数；应保留原参数，或使用已有 --devco-init-skip-seed 参数避免重写。

## 7. Responses 在未配置 reasoning_effort 时的协议分析

对于当前 GPT-5.6 Sol / Luna，缺省推理强度是合法请求，官方默认值为 medium。Responses 允许推理与函数工具同时使用，不会因为省略 effort 而触发此次 Chat 的工具兼容性错误。私有网关仍需遵循相同协议，其实际行为尚未联调。

| 原配置 | Responses 请求 | GPT-5.6 行为 |
| --- | --- | --- |
| 未配置 effort | 省略 reasoning.effort | 服务端默认 medium |
| reasoning_effort=high | 转换为 reasoning.effort=high | high |
| reasoning_effort=none | 转换为 reasoning.effort=none | 关闭推理 |
| reasoning_effort 为 null | 归一为省略，而非字符串 none | 服务端默认 medium |

未配置不是关闭推理。自动协议选择不能以“配置里有没有 effort”为条件；否则未配置的 Luna 又会落回 Chat。应先根据模型能力确定 Responses，再独立处理可选参数。

对默认未配置 effort 的主任务，可发送如下合法请求体：

```json
{
  "model": "gpt-5.6-luna",
  "input": [{ "role": "user", "content": "查看当前时间" }],
  "tools": [{
    "type": "function",
    "name": "get_current_time",
    "description": "读取当前时间",
    "parameters": { "type": "object", "properties": {}, "additionalProperties": false }
  }],
  "stream": true,
  "max_output_tokens": 128000
}
```

请求不需要 reasoning 字段。这里的输出上限沿用当前模型配置，只表示上限，不代表每次实际生成该数量。

协议切换要完整覆盖以下差异：

| 项目 | Chat Completions | Responses |
| --- | --- | --- |
| SDK 调用 | chat.completions.create | responses.create |
| 消息输入 | messages | input |
| 推理参数 | reasoning_effort | reasoning.effort，可省略 |
| 输出预算 | 现有 max_tokens / max_completion_tokens | max_output_tokens |
| 函数定义 | tools 中的 function 嵌套对象 | tools 中平铺 name、parameters 等字段 |
| 工具结果 | role=tool、tool_call_id | type=function_call_output、call_id |
| 输出解析 | choices / delta | output 条目和 response.* 事件 |
| 结构化输出配置 | response_format | text.format |

当前项目的 Responses Formatter 已实现消息、函数调用/结果及图片格式转换，模型构造已把 max_tokens 映射成 max_output_tokens。SDK 层在 Parameters 不提供有效 effort 时省略 reasoning；其 thinking_enable=false 只影响是否注入参数，不会向服务端发送“关闭推理”的指令。

本次已补充 Responses 参数转换：先把各层参数归一到同一种协议，再按单次调用 > 模型 > 提供商的优先级合并；同一层的新旧字段矛盾时给出明确错误。未配置时省略 reasoning，不擅自填 none 或 high。Shell 关闭推理开关为 0 时保留配置或默认推理行为，为 1 时仅覆盖独立审查实例的 effort=none。

三条调用链在 effort 未配置时的目标行为：

- 主任务：省略 effort，GPT-5.6 默认 medium。
- Shell guard：开启现有关闭推理开关后，仍显式发送 reasoning.effort=none，独立于主任务是否配置 effort。
- FailureLoopGate：复用主模型且不带工具，省略 effort 时也使用默认 medium；tool_choice=none 只限制工具选择，不关闭推理。

工具后续轮需要保留函数 call_id 和对应的 reasoning items。当前依赖已保存 reasoning_item_id 并在 Formatter 回传；尚未看到 encrypted_content 的完整保存/回传逻辑。因此应验证网关是否支持引用这些 ID。如果使用不保存服务端状态的模式，还需按官方协议处理加密 reasoning items，不能只验证第一轮工具调用。

当前底层 Responses 流式解析主要处理文本/函数增量和 response.completed，未见针对 response.failed、response.incomplete 的显式分支；共享 consume_model_response 也只是收集文本。迁移验收需覆盖失败、预算耗尽和中途断流，避免把未完成文本当成完整审查结论。max_output_tokens 包含推理与可见输出；FailureLoopGate 的 512 是引导长度，不能直接用作复查生成上限。

现有 GPT 配置未设置 temperature、top_p，建议继续省略，避免迁移时自动添加采样参数。Responses 不等同于所有模型都支持该接口；自动规则仍只覆盖已确认模型。

官方依据：[推理默认值及预算说明](https://developers.openai.com/api/docs/guides/reasoning)、[函数调用及 reasoning items](https://developers.openai.com/api/docs/guides/function-calling)、[Responses 迁移说明](https://developers.openai.com/api/docs/guides/migrate-to-responses)、[GPT-5.6 Sol 模型说明](https://developers.openai.com/api/docs/models/gpt-5.6-sol)。
