# Agent 定时进展提醒：代码修改方案

分析日期：2026-10-15。本文以当前工作区源码（含尚未提交的修改）为依据，是实施方案；本次仅新增本文档，没有实现功能、运行回归测试或变更部署配置。

## 1. 建议与实施边界

新增独立的 `ProgressReminderController`，在下一轮主模型推理前，按执行时间生成简短的进展检查提醒。默认间隔 600 秒，不额外调用模型，不设置后台定时任务，不中断模型或工具，不修改任务验收条件。

保留现有 `FailureLoopGate`：它负责对已完成工具记录做独立的模型审查；新组件负责定时提示主模型检查是否仍在有效推进。两个组件独立开关、独立计数，共用请求级提醒的预算和重试处理。

四种组合均为明确支持和必须验收的功能：两者都关、仅开启 FailureLoopGate、仅开启定时提醒、两者都开。不开设会覆盖两个独立开关的第三个总开关，也不使用互斥的单选 mode 作为配置来源；mode 仅从两个开关派生用于展示和日志。

第一阶段只实现定时提醒和事实统计，不新增本地语义循环判定、不自动切换工具、不自动降低推理强度，也不改变现有 FailureLoopGate 的周期。是否更换方案由主模型结合真实结果判断。

功能仅覆盖经过 `QwenPawAgent._reasoning()` 的原生 ReAct 执行。控制器本身不依赖 Windows；外部 Coding CLI、独立路由模型或没有经过该入口的模型调用不因本功能自动获得提醒。上线可以先只对 Windows 非 Coding 的部署启用。

## 2. 当前实现核对

用户所说的 failloopgate，在当前源码中的实际类名是 `FailureLoopGate`。

| 位置 | 当前行为 | 对新方案的影响 |
| --- | --- | --- |
| `src/qwenpaw/loop/gates/failure_loop.py`：`FailureLoopGate`、`build_failure_loop_gate()` | 采集当前 session/reply 的工具调用及完整结果；只在启用且 Windows 非 Coding 时装配；`check()` 始终返回 `BYPASS` | 它目前是建议机制，不是自动停止或自动拒绝重试的门禁 |
| `src/qwenpaw/loop/model_loop.py`：`ModelLoopInspector.inspect()` | 默认累计 5 个有已完成工具记录的 ReAct 工具轮后，复用主模型对象进行独立审查；同轮多个工具不是多轮 | 不是每 5 次失败，更不是每 10 分钟检查 |
| `src/qwenpaw/loop/model_loop.py`：`REVIEW_PROMPT` | 审查 repeat/similar/cycle；成功状态也可能被审查；分页、合理轮询、验证和有依据的重试不自动算循环 | 新方案不能把“成功但重复”的问题描述成现有组件完全没有覆盖 |
| `src/qwenpaw/agents/context/failure_middleware.py`：`prepare()` | 主推理前等待独立审查；有 findings 才准备临时提示；有未完成调用时跳过审查 | 新定时提醒不需要再做一次相同的模型审查 |
| `src/qwenpaw/agents/react_agent.py`：`_reasoning()` | 先处理 pending stop，再 `await _inject_failure_recovery()`，然后进入主推理 | 定时提醒的准备应放在 failure review 之后，计入本轮审查花费的执行时间 |
| `src/qwenpaw/agents/context/budget_middleware.py` | 目前只把 `is_failure_hint()` 识别的消息视为可选提醒；压缩后的重试缓存也特别处理该类型 | 必须让预算裁剪与重试恢复同时认识新提醒，不能只追加一条消息 |
| `src/qwenpaw/agents/context/request_budget.py`：`RequestSnapshot` | 重建输入时保留原请求的 prefix/suffix | 新提醒应放在请求尾部，避免写入持久对话；通过真实压缩测试确认 suffix 保留 |
| `src/qwenpaw/agents/react_agent.py`：`state_dict()` / `load_state_dict()` | 当前保存 AgentState、Scroll 与 session skills 等状态 | 可以额外保存进展提醒的版本化状态，不需要新建数据库 |
| `src/qwenpaw/runtime/builtin_commands.py`：`_save_agent_state()` | 手工构造 session payload，只保存显式传入的附加字段 | 只改 Agent 的序列化还不够；保留对话的命令也要保留新 checkpoint |
| `main.py` | 已有 failure-loop 环境映射、CLI 参数及转发 | 新配置参照该链路独立增加，不挪用 failure-loop 参数 |

现有默认值还有入口差异：`FailureLoopConfig.from_env()` 的 enabled 默认 False，但 `main.py` 的 `--failure-loop-enabled` 在环境缺省时默认是字符串 `1`。新功能应明确默认关闭，避免复制出另一个入口默认值差异。

## 3. 与 FailureLoopGate 的区别

| 比较项 | 当前 FailureLoopGate | 新 ProgressReminderController |
| --- | --- | --- |
| 目的 | 从工具证据中发现可能的重复、相似尝试和跨工具循环 | 定时要求主模型核对进展、必要验证和剩余需求，减少无效推进 |
| 触发依据 | 新完成的工具轮数，默认 5 轮 | 本次 reply 累计执行时间，默认间隔 600 秒 |
| 是否要求失败 | 不要求；成功但无意义的重复也可形成 finding | 不要求；到时间即可提醒，但不宣称已发现循环 |
| 谁做判断 | 独立 review 调用中的模型，返回结构化 findings | 下一次正常主推理中的模型，结合现有上下文判断 |
| 额外模型请求 | 有；使用当前主模型对象，沿用其配置，并可能重试/回退 | 无；只增加有限的输入 token，仍可能带来少量推理开销 |
| 输入证据 | 独立保存的当前任务工具记录，可经 Scroll 整理 | 简短时间和事件统计；实际结果仍由主上下文及既有工具结果提供 |
| 提醒内容 | 有记录编号支持的可选纠偏建议 | 条件化的进展检查，不输出本地判定的“任务已卡住” |
| 持久化 | 工作区 `failure_loop/history.db` | 现有 session snapshot 内的小型版本化 checkpoint |
| 是否强制换方案/停止 | 当前均不强制；`check()` 返回 BYPASS | 均不强制；不进入 StopHandler |
| 适用范围 | 当前写死为 Windows 非 Coding | 经过原生 ReAct 入口的请求，独立启用 |
| 一次模型调用超过 10 分钟 | 无法靠该组件改写已经发出的普通请求 | 同样不能；在调用结束后的下一次推理边界处理到期提醒 |

项目还存在 `DoomLoopGate`（`src/qwenpaw/loop/gates/doom_loop.py`）：它基于本地调用相似规则和配置阶段，可以继续提示或终止。新功能不新增第四套硬性循环处置规则，也不覆盖该组件的结果。

## 4. 调用链与协作顺序

```text
ReplyStart / 同 reply 审批或外部执行恢复
  → ProgressReminderController 绑定当前 session/reply，开始本次执行段计时
  → 工具调用与结果事件：原 FailureLoopGate 和新控制器各自观察
  → 下一轮 _reasoning()
      1. check_pending_gates：有终止决定就按现有规则返回
      2. await _inject_failure_recovery()：现有独立审查保持不变
      3. ProgressReminderMiddleware.prepare()：本地检查 600 秒是否到期
      4. 正常调用 SDK 主推理
          memory / plugin / Scroll cap middleware
          → FailureRecoveryMiddleware：追加可选故障建议
          → ProgressReminderMiddleware：追加可选定时提醒
          → RequestBudgetMiddleware：对完整请求检查预算
          → 原模型调用
  → _reply() 的 finally：结算本执行段，暂停计时
  → 原 session 保存流程：保存 checkpoint，不保存提醒消息
```

两条提示可以同轮存在，但职责分开：FailureLoopGate 提供具体重复证据，定时提醒只说明如何结合这些证据核对推进策略，不再重复列出完整 findings。

不得因为“本轮已有定时提醒”而跳过到期的 failure review；也不得因为 review 没发现问题而断言任务已经有效推进。若需要以后降低 review 频率，应作为另一个有对照实验的优化提交。

新增组件不继承 `StopGate` / `LoopGate`，不注册 StopHandler，不设置 `_gate_pending_stop`，不调用 `reset_peers`，不修改现有轮次、目标或预算限制。

## 5. 按文件划分的修改清单

### 5.1 新增文件

| 文件 | 职责 |
| --- | --- |
| `src/qwenpaw/loop/progress_config.py` | `ProgressReminderConfig`；只读取新环境变量，校验 enabled、interval_seconds |
| `src/qwenpaw/loop/progress_reminder.py` | 控制器、状态与短提示模板；时间判断、事件统计、请求级候选提醒、状态导入导出；无模型调用、无新 DB |
| `src/qwenpaw/agents/context/progress_middleware.py` | `prepare()` 和 `on_model_call()`；生成/拟合提醒，将其放入本次模型请求而非 `state.context` |
| `src/qwenpaw/agents/context/request_hints.py` | 集中识别已注册的可选请求提醒；提供 failure/progress 的精确类型判定和裁剪优先级 |
| `tests/test_progress_reminder.py` | 计时、生命周期、事件去重、独立启用和无额外模型调用 |
| `tests/test_progress_middleware.py` | 请求注入、预算、重试、fallback、Scroll、取消及任务切换 |

### 5.2 修改现有文件

1. `src/qwenpaw/constant.py`
   - 增加 `PROGRESS_REMINDER_MESSAGE_TAG = "progress_reminder"`。
   - 保留现有 failure、loop-continuation 等标签含义。

2. `src/qwenpaw/runtime/builder.py`
   - 解析新配置并构造控制器，作为可选依赖传给 `QwenPawAgent`。
   - 关闭时不装配、不增加系统提示、不产生新状态文件。
   - 当前有显式 `override.system_prompt` 的构造路径；新增静态规则应尊重这种显式覆盖。默认提示走 contributor；显式 override 路径仍可使用独立开关控制的动态提醒，不暗改覆盖文本。

3. `src/qwenpaw/agents/react_agent.py`
   - 构造器增加 `progress_reminder: ProgressReminderController | None = None`。
   - 在 RequestBudgetMiddleware 前注册 ProgressReminderMiddleware，并保持两种提醒的稳定顺序。
   - `_reasoning()`：在现有 failure preparation 后做本地 progress preparation；不放进 SDK 每次 HTTP 重试里重新计时。
   - `_reply()`：为新 reply 和已有 reply 的恢复建立执行段，用 `try/finally` 结算；不能在审批恢复时重置累计时间。
   - `_execute_tool_call()`：像现有 gate 一样观察完整调用参数，但不称该位置为“工具函数已经开始执行”，因为权限等准备仍可能发生。
   - `_reply()` 事件转发：保留原事件和顺序，为 progress 增加独立的观察函数。不要让现有 `_observe_failure_event()` 中的 `gate is None` 提前返回阻止 progress 采集。
   - 分别隔离两种观察器的异常；progress 故障不能中断工具事件和主任务，取消信号按原链路传播。
   - `state_dict()` / `load_state_dict()`：保存/恢复版本化 checkpoint；旧 session 无该字段时正常启动。
   - `close()`：仅释放控制器资源，不把 Agent 对象销毁解释成业务任务完成，不清除刚保存的同 reply checkpoint。

4. `src/qwenpaw/agents/context/failure_middleware.py`
   - `is_failure_hint()` 的判定可委托公共注册表，保持原接口兼容测试及调用方。
   - 不改 `prepare()` 的触发轮数、findings 含义、review 参数及持久化行为。

5. `src/qwenpaw/agents/context/budget_middleware.py`
   - 把可选提醒的识别从仅 `is_failure_hint()` 扩为明确注册的 failure/progress 两类。
   - `_restore_retry_request()` 中的 source IDs、hint IDs、清除旧提示及恢复新提示都要同步支持两类，不能只修改 `_omit_optional_hint()`。
   - 预算紧张时优先舍弃 progress，再考虑 failure。用户消息、其他 gate 的继续提示和工具调用/结果不得被归类为可删提醒。
   - 沿用现有完整请求压缩和最终计数逻辑；第一阶段不顺带改变现有 failure-only 请求的压缩时机。

6. `src/qwenpaw/runtime/prompt_contributors.py` 与 builder 的 prompt context
   - 新增 `ProgressExecutionContributor`，仅在该功能启用且走默认 prompt 组装时加入固定执行规则。
   - 通过 builder 传入本次解析后的配置，避免多个位置独立读环境形成差异。
   - 不把当前分钟数放入系统提示，不修改用户现有的 AGENTS.md/SOUL.md 文件。
   - 对自定义 PromptManager 未注册该 contributor 的路径保留兼容；动态提醒包含必要的质量和权限边界，静态片段不是功能正确性的唯一依赖。

7. `src/qwenpaw/runtime/builtin_commands.py`
   - `_save_agent_state()` 增加可选 `progress_reminder_block` 并逐个更新保留对话状态的调用方。
   - `/compact` 等保留同一对话执行状态的操作传回 checkpoint；清空、重置或切换任务时丢弃。
   - 不通过任意透传未知 snapshot 字段来解决问题。

8. `main.py`
   - 为新参数补全 `apply_devco_bundle_env()`、argument parser 和最终调用处的转发。
   - CLI 显式值覆盖环境值；没有参数时保留已有环境值；新功能各入口一致默认关闭。

9. 更新 `tests/test_request_budget.py`、`tests/test_failure_loop.py`、`tests/test_conversation_timing.py`，补充公共提醒机制和两种功能组合的集成覆盖。根据实际 session 命令测试入口补充状态保存回归。

`request_budget.py` 的 RequestSnapshot 默认不需要改算法：当前 suffix 保留机制适合临时尾部提醒。若真实集成测试发现身份或次序问题，再做有针对性的修复，不预先重写压缩体系。

## 6. 状态与计时语义

### 6.1 作用域

以 `(session_id, reply_id)` 隔离。新用户 reply 重置；同 reply 的审批/外部结果恢复继续；旧 reply 的迟到事件不得修改新任务。第一阶段不把多条用户消息推断为同一个业务任务，也不为 `/goal`、`/mission` 跨 reply 续跑新建第二套任务标识。

运行时主要状态建议如下，实际命名可按项目风格调整：

```python
@dataclass
class ProgressState:
    session_id: str
    reply_id: str
    execution_elapsed_seconds: float = 0.0
    last_checkpoint_elapsed_seconds: float = 0.0
    checkpoint_seq: int = 0
    observation_version: int = 0
    # 运行时私有：当前执行段起点、最近记录、去重集合、候选提醒缓存。
    # monotonic 起点和 Msg 对象不序列化。
```

### 6.2 时间含义

- 用可注入的 `time.monotonic()` 计算同进程执行段的持续时间，避免系统时钟校准影响。
- `execution_elapsed_seconds` 是 Agent 执行段时间，包含模型、failure review、工具和服务等待，不等于纯模型推理或 CPU 时间。
- 每次 `_reply()` 的执行段结束后暂停；跨请求的人工审批等待、进程停机和应用未运行的时间不累计。恢复时用新 monotonic 起点加上已保存的秒数。
- 如果人工等待发生在仍未退出的执行段内部，第一阶段按该段耗时累计；不要在缺少可靠等待事件时声称已经精确扣除。以后可用明确的生命周期信号进一步细分，不能靠“多久没有 token”猜测。
- UI 如需墙钟时间，可另存显示用时间戳；调度不依赖两个进程的 monotonic 绝对值，也不靠墙钟差补算停机时间。

### 6.3 到期与重试

```python
# 下面是调度伪代码，不是可以直接粘贴的完整实现。
decision_key = (session_id, reply_id, cur_iter)
now_elapsed = controller.current_elapsed()

if controller.has_prepared_decision(decision_key):
    return controller.prepared_decision(decision_key)

if now_elapsed - state.last_checkpoint_elapsed_seconds < interval_seconds:
    return None

candidate = controller.make_checkpoint(decision_key, now_elapsed)
state.last_checkpoint_elapsed_seconds = now_elapsed
state.checkpoint_seq += 1
return candidate
```

语义约定：

1. 600 秒到期，等下一个主推理边界；600 秒时没有边界就不注入，也不新建模型请求。
2. 阻塞到第 25 分钟才到达边界时，只生成一条当前提醒，下一次从该检查点再计 600 秒，不补发两条过期提醒。
3. 同一 decision key 的 SDK 重试、媒体兼容重试和 fallback 使用同一检查点；每个模型按其 tokenizer 重新拟合预算。固定模型下复用稳定 Msg 对象，兼容现有压缩缓存的对象身份判断。
4. 候选缓存同时记录 observation_version；任务或证据版本变化时丢弃过期候选，不向新任务投递。
5. `last_checkpoint` 表示已经处理了一次定时检查，不表示模型已经读取或接受提示。若因预算、计数错误或模型请求失败没有实际使用，记录对应结果，下一周期再尝试；不在每一轮立即重试同一提醒。
6. 区分 `prepared`、`included_in_request`、`omitted`；不能仅因 prepare 成功就记作模型已收到。`included_in_request` 也不等于模型已经采纳。

### 6.4 序列化

在现有 session payload 下增加版本化块，例如：

```json
{
  "progress_reminder": {
    "version": 1,
    "session_id": "current-session",
    "reply_id": "current-reply",
    "execution_elapsed_seconds": 642.5,
    "last_checkpoint_elapsed_seconds": 605.0,
    "checkpoint_seq": 1,
    "observation_version": 8
  }
}
```

需要跨恢复保留的累计工具计数和小型最近记录也放在这个版本化块中，使用 JSON-safe 值。去重用的 call IDs 按当前 reply 保存或从相同 reply 的现有结果恢复；不能重复累计已保存的历史结果。

拒绝不匹配的 session/reply、未知版本和非法计时值（包括 NaN/Infinity/负数）；仅忽略坏的进展块，不使整个旧 session 无法加载。配置关闭时不因旧 checkpoint 自动启用。

## 7. 事实采集与证据边界

新控制器不依赖 FailureLoopGate 开启，也不访问或启动它的 history.db。允许二者观察同一批原始事件，不额外执行任何工具。

第一阶段只采集：

- 当前 reply 下工具调用数、终态分布、已知 pending/offloaded 数；同一 call ID 的重复事件去重。
- 最近最多 16 条简短记录：call ID、工具名、iteration、状态、operation signature、result signature。
- 对工具名和规范化参数生成操作签名；对实际文本结果做增量摘要时只更新哈希，不再缓存一份完整输出正文。非文本结果仅标识“存在非文本结果”，不推断其内容。
- 展示“同一操作签名及结果签名出现 N 次”时，明确它只是重复观察，不是无进展判决；不同签名也不证明进展。

完整 call ID 去重集合随本 reply 的工具数量增长，任务结束/切换后释放；不要把整个组件宣称为严格常量内存。最近记录窗口是有界的，不等于全部历史证据。

成功调用、写入文件、结果哈希变化、生成文字、工具调用数量都不能单独充当“已验证任务进展”。没有正式的需求/里程碑状态时，不编造 `verified_progress` 或剩余需求清单；让主模型根据原始用户要求核对。

`offloaded=true` 以及尚未回传实际结果的调用不能计为业务操作已经成功完成。参数生成的 ToolCallStart 也不能当作工具执行起点。若完整工具调用/结果尚未配对，推迟到正常安全的主推理边界，不插入消息破坏协议。

## 8. 提示词

### 8.1 固定执行规则

在功能启用并走默认 prompt 组装时加入一次，按 agent language 提供 zh/en 版本；其他语言可回退 en。以下为 zh/en 版本：

zh：

```text
在完整满足用户要求和既定验收标准的前提下，减少无效往返、加快执行节奏，尽快推进并交付任务。
复用已确认的事实和已有成果，避免无新证据的重复调查、重复计划和重复验证。
信息足够支持下一步时应立即行动：直接调用工具或给出结果，不要只描述打算做什么，也不要在没有实际动作的情况下以“接下来我会……”这类话结束；减少解释性输出和重复确认。
工具执行和验证要持续到任务完成：空结果、部分结果或范围可疑的结果，先换查询或换方法重试，再下结论。
同一操作在实质相同条件下反复出现同类失败且没有新信息时，不原样重试；先根据失败原因补齐缺失条件、调整关键条件、验证新假设或选择其他可行路径。暂时性故障按工具规则有限重试。
分页、不同目标的处理、必要验证以及有进展的等待不自动算循环。
宣布完成前，逐项核对原始需求和验收标准；“完成”指每一项都已验证，而不是可能性较大的子集。达到验收标准后及时交付；尚未完成且仍可推进时继续执行。
真正缺少必要输入、权限或外部条件时，直接说明具体缺什么、已尝试过什么，不要用反复重试代替说明。
定时提醒不改变权限、任务范围、必要验证、停止条件或已有并行规则。
```

en：

```text
While fully meeting the user's requirements and the established acceptance criteria, reduce wasted round-trips, pick up the pace, and make progress and deliver promptly.
Reuse confirmed facts and existing results; avoid repeated investigation, re-planning, and re-verification that add no new evidence.
When the information needed for the next step is available, act immediately: call the tool or produce the result directly — do not merely describe what you intend to do, and do not end without any actual action on a promise like “I will now ...”; keep output concise and avoid repeated confirmations.
Keep executing and verifying until the task is complete: for empty, partial, or suspiciously narrow results, retry with a broader or different query or method before drawing conclusions.
When the same kind of failure recurs under materially identical conditions with no new information, do not retry unchanged; first fill in the missing conditions, adjust the key conditions based on the failure cause, test a new hypothesis, or choose another viable path. For transient failures, retry only within the tool's allowed limits.
Pagination, handling different targets, required verification, and waits that show progress do not automatically count as loops.
Before declaring completion, check every original requirement and acceptance criterion item by item; “complete” means every item has been verified, not a plausible subset. Deliver promptly once the acceptance criteria are met; keep going while the task is unfinished and still actionable.
When required input, permission, or external conditions are genuinely missing, state exactly what is missing and what has already been tried — do not substitute repeated retries for explaining the blocker.
The timed progress reminder does not change permissions, task scope, required verification, stop conditions, or the existing parallel-dispatch rules.
```

### 8.2 每次到期的动态提醒

采用单个 `Msg(name="progress_reminder", role="user")`，匹配现有 failure hint 的请求适配惯例，并用受控 metadata 识别；不会因为写了 `<system-reminder>` 就真的提升为 system 权限。以下为 zh/en 模板：

zh：

```text
<system-reminder>
执行进展检查：本次 reply 累计执行 {elapsed_minutes} 分钟，距上次检查 {since_checkpoint_minutes} 分钟。
已观察到的工具事件：{bounded_factual_stats}。以上仅为事实统计，不等于任务进展或循环判定，也不构成新任务或验收标准变更。

请结合原始需求和最近真实结果简短核对，并适当加快推进节奏；若本轮附有故障建议，将其作为参考：
1. 当前路径仍在产生有效结果时继续，不因耗时较长就重启或换方案。
2. 同类失败反复发生、或重复操作没有新信息时，从最近一次失败的真实原因出发（而不是换个说法重试同一操作），调整关键条件或切换可行路径，并执行一个可验证的下一步。
3. 信息已足够就立即行动或交付——直接执行下一步，不要只描述计划；减少解释性输出与重复确认，避免额外扩展，完成必要验证后尽快交付。
4. 不降低验收标准，不跳过必要验证，不突破既有权限和执行限制。
5. 仍有可执行路径就继续；仅在真正缺少必要输入、权限或外部条件时说明具体阻塞，并写清已尝试过什么。

这不是任务截止时间，也不证明你已经陷入循环，不代表需要收尾或缩小任务范围；核对无异常时可直接继续任务，并以更快的节奏推进剩余工作。无需专门回复本提醒或输出长篇自检。
</system-reminder>
```

en：

```text
<system-reminder>
Progress check: this reply has been executing for {elapsed_minutes} minutes in total, {since_checkpoint_minutes} minutes since the last check.
Observed tool events: {bounded_factual_stats}. These are factual statistics only — they are not a judgment of task progress or a loop, and they do not add new tasks or change the acceptance criteria.

Briefly check against the original requirements and the latest real results, and pick up the pace where appropriate; if a failure hint is attached this turn, use it as reference:
1. If the current path is still producing useful results, continue — do not restart or switch approaches just because it is taking long.
2. If the same kind of failure recurs, or repeated operations yield no new information, start from the true cause of the most recent failure (instead of retrying the same operation reworded), adjust the key conditions or switch to a viable path, and take one verifiable next step.
3. If the information is sufficient, act or deliver now — take the next concrete step directly instead of only describing the plan; keep output concise and avoid repeated confirmations, avoid extra scope, and deliver promptly once the required verification is done.
4. Do not lower acceptance criteria, skip required verification, or exceed existing permissions and execution limits.
5. Continue while an actionable path remains; state the specific blocker only when required input, permission, or external conditions are truly missing, and say what has already been tried.

This is not a task deadline and does not prove you are stuck in a loop, nor does it mean you should wrap up or narrow the task scope; if the check shows nothing abnormal, just continue the task and move the remaining work forward at a faster pace. No need to reply to this reminder or produce a long self-review.
</system-reminder>
```

metadata 至少包含：内部 tag、source、session_id、reply_id、iteration、checkpoint_seq、observation_version。只有内部登记的 tag/source/name/role 组合且归属当前请求的对象才属于可选提醒；不按消息正文匹配，不把用户粘贴的同样文字判为内部消息。

动态事实只放程序生成的短统计，不原样拼接工具输出、文件正文或日志里的指令。无需再调用模型概括历史；缺少的统计写“未知”或省略。

## 9. 预算、重试和持久上下文

1. 新 middleware 只构造本次 `input_kwargs["messages"]` 的新列表，不向 `agent.state.context` append，不调用 `_save_to_context()`，不进入 Scroll archive 或长期 memory。
2. 每个主请求中至多一条 progress hint；重试去重只处理精确识别的本类临时消息，不删除用户内容或另一类提醒。
3. progress 提醒使用内部固定的 512 token 输入上限，不对外提供长度配置，也不改变主模型或 review 的生成预算。使用本次 `current_model.count_tokens()`，fallback 重新计数，不更改 provider 的共享配置。
4. 先减少可选统计明细，再使用保留全部必要约束的完整短版模板；仍不适配时整条舍弃。不要按任意字符/token 边界截断规则，避免切掉否定和约束。
5. 最终 RequestBudgetMiddleware 仍对系统提示、全部动态内容和工具 schema 一起计数。预算裁剪优先 progress 后 failure；保留原请求无法适配时仍按现有规则报错。
6. 当前 `_omit_optional_hint()` 只有“移除全部 failure 后能适配才采用”的路径。推广到两类后需要顺序尝试候选删减集合，而不是一个模糊的通用删除规则。
7. 没有装配 Scroll/RequestBudgetMiddleware 的路径，progress 仍执行自身 token 上限；不借此关闭 SDK 原有上下文限制，也不声称完成了新的全请求预算治理。
8. `RequestSnapshot` 压缩重建后不得丢失/复制 suffix；SDK 媒体重试、fallback 与已压缩请求恢复时，不把过期 progress hint 带到下一 iteration 或 reply。
9. 确认辅助 review 的调用不经过 progress middleware、不触发第二层提醒。该组件不向 Shell guard、模型探测或 Scroll 摘要调用注入文本。

## 10. 配置

| 环境变量 | 默认值 | 对应 CLI | 语义 |
| --- | --- | --- | --- |
| `QWENPAW_PROGRESS_REMINDER_ENABLED` | `0` | `--progress-reminder-enabled` | 独立启用定时提醒 |
| `QWENPAW_PROGRESS_REMINDER_INTERVAL_SECONDS` | `600` | `--progress-reminder-interval-seconds` | 两个检查点之间的最短执行段累计秒数 |

布尔值和非法配置回退/日志风格与 FailureLoopConfig 保持一致；间隔正整数拒绝 bool、非正数。提醒长度使用内部固定的 512 token 上限，不提供对应 CLI 或环境变量；不足时使用完整短版，而不是截断。

两套变量不互相替代。例如：

```powershell
# 以下为实施后可用的配置示例，本次没有执行。
$env:QWENPAW_PROGRESS_REMINDER_ENABLED = '1'
$env:QWENPAW_PROGRESS_REMINDER_INTERVAL_SECONDS = '600'
```

不把新变量写到 provider JSON；变量应传给实际 Paw 启动进程。main.py 默认关闭，标准 CLI/库读取环境的入口也保持关闭；已有 FailureLoopGate 开关保持原样。

### 10.1 两个独立开关与四种组合

以下 F/P 指两个开关的最终配置值。FailureLoopGate 的平台和模式限制仍需单独判定；表内运行行为以两个功能均适用的原生 Windows 非 Coding 请求为例。

| F：`QWENPAW_FAILURE_LOOP_ENABLED` | P：`QWENPAW_PROGRESS_REMINDER_ENABLED` | 派生显示模式 | 执行行为 |
| --- | --- | --- | --- |
| `0` | `0` | `off` | 两种组件均不装配；没有相关事件采集、独立 review、提醒或新增固定执行片段；仍保留其他既有门禁及正常任务执行 |
| `1` | `0` | `failure_only` | 原 FailureLoopGate 按完成工具轮数审查，有 findings 时注入故障建议；不启用定时计时或 progress 提示 |
| `0` | `1` | `progress_only` | 控制器独立计时，到期后在下一主推理中提醒；没有独立故障 review，也不创建或读取 failure_loop/history.db |
| `1` | `1` | `both` | 两者分别按自身条件触发；同轮都到期时先故障审查，再准备定时提醒；最终请求可以含两条不同类型的可选提示 |

启用不是立即注入：F 开启但未到工具轮阈值、或者没有有效 finding 时，不应强行发一条故障提示；P 开启但未满 600 秒时不发定时提示。因此 `both` 代表两个机制都可用，不代表每轮都必须出现两条提示。

明确区分“未设置”和“显式关闭”：最终 enabled=False 必须保留，不能使用 `cli_value or env_value or default` 这样的真假值回退。

### 10.2 代码装配方案

配置在本次 Agent 构造时分别解析并固定，两个组件分别构造、观察事件和执行 preparation。下面是结构伪代码，factory 的 config 注入参数属于待新增接口：

```python
failure_config = FailureLoopConfig.from_env()
progress_config = ProgressReminderConfig.from_env()

# 工厂仍保留 Windows / 非 Coding 等适用性判断。
failure_gate = build_failure_loop_gate(
    config=failure_config,
    workspace_dir=workspace_dir,
    request_context=request_context,
) if failure_config.enabled else None

# 不以 failure_gate 是否存在作为条件。
progress_reminder = ProgressReminderController(
    config=progress_config,
) if progress_config.enabled else None

agent = QwenPawAgent(
    # 其余现有依赖略。
    failure_loop_gate=failure_gate,
    progress_reminder=progress_reminder,
)
```

具体要求：

1. `build_failure_loop_gate()` 增加可选的显式 config 参数；未传时仍沿用现有 from_env 行为，兼容旧调用方。配置只需解析一次，不改变 failure 的适用条件。
2. 两个 middleware 分别注册；二者都存在时顺序固定为 failure、progress、最终 RequestBudget。只存在一个时，它仍在预算 middleware 前；二者都不存在时不插入空的提醒 middleware。
3. `_reasoning()` 中分别判断可选依赖。不能把 progress preparation 放在 `if failure_gate is not None` 分支内；反方向也一样。
4. 事件观察分别使用异常边界。一个组件发生普通异常时记录并跳过该组件，不自动关闭、启用或触发另一个。取消信号仍沿原执行链传播。
5. Progress 的固定提示片段只依赖 P 的有效启用值；只开 F 时不添加 progress 的静态规则。Progress 动态模板自身完整，不要求 failure findings 一定存在。
6. 共享的 request_hints 只做消息识别、预算和重试辅助，不承担启用决策、计时或模型调用。
7. 两者都关时忽略各自已有 checkpoint，不因旧状态自动启用。关闭状态下不新增相关状态或访问相关历史库，也不主动删除用户以前产生的 failure 数据库。

不建议在每个事件里重新读取环境开关：一次 reply 中途改变装配状态容易造成半段采集和半段提示。第一版使用现有启动配置方式，修改启动参数/环境后按现有机制重启生效；不把它描述为已经具备在线热切换。

### 10.3 配置优先级、默认值与有效状态

对每一个开关独立应用 `显式 CLI 参数 > 对应环境变量 > 对应入口已有默认值`。其他开关的值不参与回退，也不根据历史状态、review 是否失败、是否已经到期来反推 enabled。

第一阶段保留 FailureLoopGate 现有入口默认值：库路径缺省关闭，main.py 缺省开启；Progress 在所有入口缺省关闭。本方案不为实现四种组合顺带改变已有部署的 failure 默认行为。部署配置应显式写出两个 enabled，确保跨入口获得相同组合。以后若统一所有入口默认都关闭，应独立处理兼容迁移，不在本次隐含修改。

建议 builder 记录一次最终装配日志：

```text
ReminderConfig failure_configured=1 failure_active=1 failure_reason=enabled
               progress_configured=0 progress_active=0 progress_reason=disabled_by_config
               configured_mode=failure_only effective_mode=failure_only
```

`configured_mode` 和 `effective_mode` 均由两个布尔值派生，仅用于说明。例如 Linux 请求配置 both，但 FailureLoopGate 仍因 unsupported_platform 未装配，则应显示 configured_mode=both、effective_mode=progress_only，并记录原因。不能显示“both 已生效”掩盖适用范围限制。

### 10.4 四种部署配置示例

以下为实施后的配置示例，每次选择一组传给实际启动进程。本次未执行，也不假设任意 .env 文件会自动加载。

```powershell
# 两者都关闭
$env:QWENPAW_FAILURE_LOOP_ENABLED = '0'
$env:QWENPAW_PROGRESS_REMINDER_ENABLED = '0'

# 仅开启 FailureLoopGate
$env:QWENPAW_FAILURE_LOOP_ENABLED = '1'
$env:QWENPAW_PROGRESS_REMINDER_ENABLED = '0'

# 仅开启定时提醒
$env:QWENPAW_FAILURE_LOOP_ENABLED = '0'
$env:QWENPAW_PROGRESS_REMINDER_ENABLED = '1'

# 两者都开启
$env:QWENPAW_FAILURE_LOOP_ENABLED = '1'
$env:QWENPAW_PROGRESS_REMINDER_ENABLED = '1'
```

上述四组不能连续执行后期望保留四种模式；同一进程环境最终只会保留最后一组值。CLI 的对应选项为 `--failure-loop-enabled` 与新增的 `--progress-reminder-enabled`，同样分别接受 0/1。

间隔和 token 上限只影响各自已启用的组件；仅配置 interval 不代表启用，F/P 都关闭时不会为了统计或校验提示而产生额外模型调用。

## 11. 测试与验收

全部计时测试使用 fake monotonic clock，不等待真实 10 分钟。网络调用使用模拟模型；需要真实 SDK 控制流的集成测试沿用现有测试方式。

新增四种配置的参数化组合测试，覆盖全部 `(F, P)` 值。对每一组分别断言最终装配、事件采集、独立 review 次数、动态提示类型、progress 固定片段、状态保存和新文件副作用；不能只检验两个字段的值。

另需验证：CLI 的显式 0 覆盖环境的 1；缺省 CLI 保留环境的 0；单独设置另一开关不能改变该值；旧 snapshot 不复活已关闭的组件；both 中一类普通错误不阻止另一类正常工作。平台适用性用独立参数覆盖 configured/effective mode 的差异。

| 场景 | 必须满足的行为 |
| --- | --- |
| 599 秒 / 600 秒 | 前者不准备，后者在下一推理前准备一条 |
| 25 分钟才出现推理边界 | 一条当前提醒，没有过期补发风暴 |
| 同一 iteration 的 SDK/媒体重试 | 同一个 checkpoint，不重复累计计时周期；稳定模型复用提示对象 |
| fallback 模型 tokenizer/窗口不同 | 重新拟合，必要时省略；主请求仍正常遵守其预算 |
| failure off / progress on | 有提醒，没有独立 review，没有创建 failure_loop/history.db |
| failure on / progress off | 原 review 轮数、请求和结果保持不变 |
| failure off / progress off | 无两类提醒 middleware、采集、review 和固定片段；正常模型请求及其他既有门禁不受影响 |
| 两者同时到期 | 先 review，再准备 progress；不再多一次模型调用 |
| 两者开启但只有一类到期/有 findings | 只注入实际满足条件的类型，不为凑齐两条提示额外调用模型 |
| 有 pending stop | 两种 preparation 都不执行，原停止行为优先 |
| 工具失败后更改关键条件成功 | 不因到时间强制换路线或自动停止 |
| 分页、合法轮询、正常验证 | 只展示事实，不产生本地“已陷入循环”的断言 |
| 工具结果包含注入文本 | 统计中不携带正文指令，不改变系统规则 |
| 调用/结果未配对，或 offloaded | 不破坏配对、不误记完成；不重复启动工具 |
| 同一个结果重复到达 | 事件计数和最近记录不重复 |
| 新 reply / 旧 reply 的迟到事件 | 新任务独立计时，旧事件不污染 |
| HITL/外部执行后新建 Agent 恢复 | 相同 reply 接续累计秒数，不累计跨请求等待，不重放旧提醒消息 |
| session 状态无新增字段/字段损坏 | 兼容旧数据，坏的附加块不阻止旧会话加载 |
| /compact / 清空或重置 | 前者按命令语义保留 checkpoint，后者清除；原 Scroll/skills 不丢失 |
| Scroll 压缩与重试请求缓存 | 提醒不丢失/复制/跨轮带出，用户与工具内容保持完整 |
| 提醒导致超预算 | 依次舍弃可选提醒；原本可适配的请求不被提醒阻断 |
| 模型返回最终回答或发生取消 | 不额外启动“补发提醒”请求；取消按原规则传播 |
| 功能关闭 | 无新模型输入、新系统片段、新持久化状态及新 DB |

实施后建议先执行有直接关联的回归：

```text
python -m pytest tests/test_progress_reminder.py tests/test_progress_middleware.py tests/test_failure_loop.py tests/test_model_loop.py tests/test_request_budget.py tests/test_conversation_timing.py -q
```

再运行修改涉及的 prompt、session 命令及原生 Coding/非 Coding 装配测试。新增测试文件尚不存在，上述是实施后的验收命令，不是本次已经运行的测试。

## 12. 可观测性与效果评估

只记录 session/reply/iteration、checkpoint_seq、elapsed_seconds、since_checkpoint_seconds、事实计数、hint_tokens、prepare_elapsed_ms、结果及省略原因。不新增工具正文、完整参数、思维链或用户文件内容日志。

建议事件：`checkpoint_due`、`hint_prepared`、`hint_included_in_request`、`hint_omitted`、`state_restored`。省略原因至少区分 disabled、not_due、pending_tools、stale、token_budget、count_error；包含请求不代表模型已采纳。

对相同任务与环境比较四组：两者都关、仅 FailureLoopGate、仅 progress、两者都开。固定任务验收标准、模型及其参数，记录：

- 验收通过率、遗漏/错误及提前宣称完成的比例。
- 成功任务的端到端耗时中位数和 P95，同时单独记录失败任务，避免只挑成功样本。
- 主模型轮数、review 次数与耗时、输入/输出/推理 usage、工具重试数量及有依据判定的无效重复。
- 定时提醒实际加入请求的次数、预算省略次数、主模型是否在提醒后产生可验证的有效调整。

不承诺固定提速比例；如果成功率或完整性下降，即使更早结束也不能算优化成功。提示词只能引导，不能代替验收和日志证据。

## 13. 建议落地顺序

1. 配置、控制器、原生 ReAct 生命周期与纯定时短提醒，默认关闭；不新增语义判定。
2. 请求级提醒公共识别、预算裁剪、重试/fallback 与 Scroll 集成。
3. session checkpoint、审批恢复和内置命令保存回归。
4. 固定 prompt contributor、完整组合测试和日志，再对少量部署启用。
5. 对照实验确认有效后，才考虑异常提前触发或调整 FailureLoopGate 审查周期。

“连续两次失败就提前提醒”暂列后续：应由事件提供异常信号、由现有模型判断语义，不能用工具状态或哈希直接替代 FailureLoopGate 的 review，更不能形成另一个自动停止或自动绕过权限的机制。
