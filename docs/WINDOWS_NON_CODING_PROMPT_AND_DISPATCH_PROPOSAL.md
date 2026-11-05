# Windows 非 Coding 模式：提示词与工具调度综合修改方案

核对日期：2026-10-15。状态：已按用户“先通过提示词”的要求接入提示词阶段；下文运行时校验、权限隔离、调度配置与新接口仍为后续方案，尚未实施。

本文以当前工作区源码和已安装的 AgentScope 2.0.4 为依据。已有的 Shell thinking 开关和耗时日志与本文是不同的改动。本文不修改三个本地模型的 thinking 策略，不取消权限检查、审批、Skill 加载或专业角色路由。

最新规则：`list_agents` 与 `list_skills` 在每个任务开始时实际调用；同一目标的补充、继续、纠错、ReAct 迭代与 Scroll 压缩复用本任务有效发现，不按用户消息重新列举。两个调用互不依赖，可同轮提交，不限定平台、模式、先后或固定分页大小，也不要求批次只能包含这两个调用；必要详情丢失先取回原结果，再按需补页或刷新受影响列表。Skill 动态参数仍按原有用户轮规则刷新。此次取消的是提示词中的固定调用参数，工具自身的分页默认值与取值范围不变。

下文“每用户轮双发现”及串行发现示例保留为早期方案记录，已被上述任务边界和可同轮调用规则取代，不作为当前提示词使用。当前实现以中文 AGENTS / SOUL、shell_policy 和中英文 Scroll 提示词为准。Scroll 主要保留标题索引与可取回的原始历史，不保证完整目录常驻摘要；本次增加任务续接信息与优先取回原列表的提示，并同步调整可选索引生成提示，未增加运行时任务 ID、目录固定驻留或任务调度机制。

本次实际落地范围：修改中文默认 AGENTS / SOUL、现有环境提示入口中的 Windows 非 Coding 调度文案、Shell 原子与提交说明、Shell guard 的职责说明，以及中英文 Scroll 的前置顺序文案。复用 `build_tool_usage_guidance` 注入，不新增 Contributor 或工具，不修改工具执行器、权限实现、LLM 参数、thinking 开关、FailureLoopGate 行为或并发配置。其他语言及角色通过 Windows 非 Coding 环境提示获得通用提交规则，其角色职责保持原样；现有工作区模板如何更新仍遵守原有同步机制。

这是提示词引导，不是运行时强制校验，也不能修复下文讨论的共享权限状态或保证模型一定同轮提交。需要通过新运行日志验证行为；本文中的运行时设计继续保留为后续参考。

提示词阶段现已进一步做等义精简，当前长度与条款核对见 [Windows 非 Coding 提示词精简核对](WINDOWS_NON_CODING_PROMPT_COMPACTION.md)。下文的长短文案保留用于解释原方案，实际注入以源码为准，不会同时注入本文中的多个版本。

## 1. 建议与适用边界

建议同时处理四件事：消除提示词的重复与冲突；要求模型把已经就绪的独立查询放进同一次回复；为每次工具调用隔离权限状态；由运行时决定实际并发数量和执行屏障。

“同轮提交”和“同时执行”必须分开。模型在一次 assistant 回复中可以提交多条参数已经确定的独立查询；运行时可以受并发上限约束分批执行，也可以把不适合并发的调用串行执行。不能把 `is_concurrency_safe=True`、Shell 的 `allow_shell` 或用户允许执行，解释成“操作只读且可以并发”。

新调度策略首先覆盖 Windows、有效 `is_coding_mode=False`、项目当前直接执行路径。Windows 非 Coding 的通用提示词可覆盖其他执行后端，但不能向其宣称尚未实现的并发能力。Coding 模式及其他平台不因本方案改变调度行为。权限状态隔离若准备推广到其他模式，应单独做回归。

这里的四个术语统一如下：

| 术语 | 含义 |
| --- | --- |
| 用户轮 | 一次用户请求及其处理过程 |
| 模型轮 | 主模型生成一次 assistant 回复；一条用户请求可能包含多个模型轮 |
| 工具调用 | 一个有独立 call ID、参数、权限判断和结果的调用 |
| 工具批次 | 执行器安排的一组调用；同一模型回复可以被执行器拆成多个批次 |

Shell 的“一次调用一个原子操作”不等于“一次模型回复只能调用一次工具”。FailureLoopGate 的复查间隔按其实现中的工具轮计数，不应与工具调用个数或本文的并发槽位混为一谈。

## 2. 当前实际注入链与问题

默认系统提示词来自：Agent 身份 → 工作区 `AGENTS.md / SOUL.md / PROFILE.md`（文件顺序可配置）→ 多模态提示 → Coding 提示 → Scroll 提示 → Driver 提示 → 环境和工具使用提示。具体由 `runtime/prompt_contributors.py` 和 `PromptManager` 拼接。

Contributor 的 priority 只决定拼接顺序，不创造指令优先级。不能保留前面互相矛盾的要求，再期望最后追加一段“并行优先”覆盖它们。当前实际注册的是 `WorkspacePromptFilesContributor`，不是把旧的 `AgentsMdContributor`、`SoulMdContributor` 再重复注册一次。

| 位置 | 当前事实或风险 | 应如何处理 |
| --- | --- | --- |
| `agents/md_files/zh/AGENTS.md` | 现有源码允许后续复用目录和按需发现 Skill；这与用户最新的每轮双发现要求不同 | 将相关条款统一改为每用户轮实际调用两个列表工具；普通工具并发不自动触发多 Agent 流程 |
| `agents/md_files/zh/SOUL.md` | 独立重复首工具要求，没有完整表达每轮双发现流程 | 统一引用 AGENTS 的每轮双发现规则，不保留另一套流程 |
| `config/shell_policy.py` | 独立步骤拆开后又写“依据上一条结果决定是否继续” | 明确：独立查询同轮提交；有结果依赖的操作等待结果后再发 |
| 同文件的 dispatch guidance | 并行规则只在 Shell 描述里，且把“只读命令”与实际并发近似等同 | 系统层表达提交规则，运行时表达执行能力；Shell 条件并发单独处理 |
| `app/chats/utils.py` | Skill 使用规则要求先读完整 SKILL.md，容易与 AGENTS 的 `Skill` 加载入口冲突 | 完整正文优先由 `Skill` 加载获得；只有明确满足现有兜底条件时才读文件 |
| 同文件的 Skill workflow | “按步骤顺序执行”“仅在流程允许时并行”没有解释哪些顺序不可改变 | 保留明确顺序、分支与验证；只对流程允许且无结果依赖的步骤做同轮提交 |
| 同文件的 Skill 创建规则 | “不要求某个创建 Skill”与 AGENTS 指定 skill-creator 的条款不一致 | 环境层只讲所有权、路径和注册，不再额外取消或新增创建 Skill 的要求 |
| AGENTS、Scroll 提示 | “首个工具必须 list_agents”与“当前请求缺失时先 recall”存在边界冲突 | 按每轮双发现约束，先完成发现，再按需恢复请求；同步修改 Scroll，不能保留无条件 recall-first |
| `runtime/builder.py` 与 `CodingModeContributor` | 工具有效模式根据是否有启用的 project_dir 决定；Coding 提示主要检查 enabled，还可能重新读盘 | 由 Builder 生成一次有效模式快照，所有提示、工具过滤和门禁使用同一结果 |
| 文件查找提示 | 有挂载目录优先级、默认根、只读挂载和输出根规则 | 并行规则不得把同一次有优先级的查找变成无序全盘搜索 |
| `governance/tool_adapter.py` | `_qp_raw_params`、决策、审批目标等保存在共享实例 | 同一个工具多次并发前必须隔离每个调用的完整权限生命周期 |
| `ToolDescriptor` / 本地 workspace | 项目没有明确的并发声明；包装后的 FunctionTool 默认 concurrency_safe=True | 默认值不是安全审查结论，应补明确能力和受审名单 |

另有两条需要保留的场景约束：

1. `local/zh/SOUL.md` 是 local Agent 模板，不是“模型名称属于本地模型”就一定生效。它要求复杂任务借助 make_plan。调度提速不能暗中删掉这项角色约定，也不能把它套用到所有使用本地模型的 Agent。
2. `qa` 模板、定制工作区文件、Driver 和 Skill 都可能增加流程。新规则只合并其中允许合并的就绪查询，不重写专业角色职责。`override.system_prompt` 目前能绕过默认构建，需要明确它是否接收平台运行规则；不能只新增 Contributor 就声称所有构建路径均已覆盖。

## 3. 拟修改的提示词全文

### 3.1 新增系统层 Windows 非 Coding 调度块

建议用 `WindowsNonCodingDispatchContributor` 注入。文本保存在单一策略模块，能力信息由最终实际工具集生成，不由模型或一份静态名称清单猜测。

```text
Windows 非 Coding 模式的工具提交规则

本节只适用于当前 Windows 非 Coding 请求。它规定如何组织工具调用，不扩大工具能力、文件访问范围、用户授权或并发权限。

1. 每个用户轮都先实际调用 list_agents 和 list_skills，按既定顺序取得本轮目录，再完成专业角色与技能匹配、所需 Skill 加载、必填参数核对及适用授权。即使上一轮已有目录或已知适用 Skill，也不得省略这两个发现调用。同一用户轮内可复用本轮有效结果，不必在每个模型轮重新调用。

2. 每次准备调用工具时，收集为当前目标所必需、参数已经确定、前置条件已经完成的查询。查询之间不存在结果依赖或共享可变状态冲突时，应尽量在同一次 assistant 回复中发出多个独立 tool_call，不要对每个查询分别等待一轮模型回复。不要为了增加并行数量添加无关查询。

3. “先查出文件路径再读取该文件”“先发现版本再运行该版本”“先加载 Skill 动态参数再执行脚本”属于结果依赖。必须取得前一步的实际结果后，才能构造后一步参数；不得预填猜测值并放在同一回复中。仅由执行器按顺序运行，并不能补全未知参数。

4. 同轮提交不保证同时执行。运行时根据当前工具、具体调用与并发上限安排执行。共享页面或桌面状态的操作、写入、安装、删除、发布、审批以及无法确认是否相互影响的操作按其既有顺序和权限规则处理，不与观察这些操作结果的查询组成并发组。

5. Skill 明确规定的步骤顺序、分支条件、必需验证与审批必须保留。只有该流程允许、且没有结果依赖或状态冲突的步骤才能合并提交。不能仅因两个步骤都调用只读工具，就认定可以并行。

6. 文件访问遵守现有授权和定位规则。明确的授权路径可以省去位置发现，不能省去权限检查。同一次有挂载优先级的文件查找按原顺序推进；不要为并行扩大搜索范围。不同查询确实独立时，才可合并提交。

7. 每个调用分别处理权限和结果。单个调用失败后，保留其他已取得的有效结果，修正失败原因后只重试必要部分。pending、已提交和后台运行中均不代表成功；依赖这些任务的操作与最终完成声明要等待实际结果。

8. 证据足以完成目标且必要验证通过后立即交付，不为了凑流程重复读取、探测版本或验证。历史结果只有在仍适用于当前问题时才复用；有关当前状态的结论不得只凭旧记录给出。

当前可见工具及执行能力：
{由运行时根据最终工具集和已生效的调度策略渲染；不显示未暴露工具，不把候选能力写成已实现能力}
```

该块不要求每轮再进行一次“规划模型调用”，不要求输出推理过程，也不增加专门的批量工具。模型在原有推理轮中直接生成多个原生 tool_call。

上面是用于检查规则边界的评审全文。正式注入建议采用下面的短版，具体定义由 AGENTS、现有权限与工具规则承接；不要把长短两版一起注入：

```text
Windows 非 Coding 工具提交规则：
- 每个用户轮都实际调用 list_agents 和 list_skills，再完成匹配和所需 Skill 加载；不得用历史目录或缓存替代。两项结果取得前不开展业务查询。同一用户轮内可复用本轮有效结果。
- 将当前目标所需、参数已知、前置已满足且互不依赖的查询，尽量放在同一次回复的多个 tool_call 中。不要逐条等待模型往返，也不要为凑并发增加查询。
- 路径、版本、URL 或 Skill 参数需要前一步结果时，先取得实际结果再构造后一步调用。只读不等于独立；Skill 明确顺序、挂载查找优先级、审批和共享页面状态都须保留。
- 每个 Shell 调用仍只做一个原子操作；这不限制同次回复可提交多个独立调用。实际是否并发和并发数量由运行时决定。
- 修改、安装、删除、发送和不确定操作保留原顺序与权限。每个调用独立审批、返回结果；pending 不等于完成。保留其他有效结果，只重试必要的失败部分。
- 证据充分且必要验证通过就交付。历史证据仅在仍适用时复用，不能证明外部现状。
{当前工具的实际并发能力摘要}
```

环境区不再重复长篇调度规则，Shell 描述只保留该工具特有的原子边界和简短指引。既有 AGENTS 中的安全和路由约束不为缩短提示而删除。旧日志出现约 2.4 万输入 token 的请求，包含整次请求的系统、工具、历史等内容，不能把它全部归因于 AGENTS；应记录各来源长度及实际 API usage，再决定精简范围。

### 3.2 AGENTS 的最小修改

将现有“首次发现”“跨用户轮允许复用”“已知技能足够时不调用 list_skills”以及“轻量回应无需列举”等相关条款统一改为下面的每轮规则；不能只在末尾追加新要求而保留相反的旧条款。发现与加载分开：每轮必须发现两个目录，只在使用技能时加载对应 Skill。

```text
普通工具的同轮提交或并发执行，本身不构成复杂协作态，也不自动要求创建或调度多个 Agent。是否进入复杂协作态仍取决于任务范围、判断难度、风险及实际协作需要；专业角色和 Skill 的既有匹配要求仍须执行。

在 Windows 非 Coding 模式下，完成必要发现、匹配和 Skill 加载后，按系统中的工具提交规则组织调用。已就绪的独立查询尽量在同一次回复中提交；依赖前一步返回值、明确流程顺序或共享可变状态的步骤，取得结果后再推进。每个 Shell 调用一个原子操作，不限制同次回复中独立调用的数量；实际并发由运行时控制。
```

每轮发现规则写为：

```text
每个用户轮开始时，先调用 list_agents，再调用 list_skills，取得本轮目录后重新匹配专业 Agent 和 Skill。两个调用均不得省略，不因轻量回应、已知技能、上一轮目录仍可见或缓存未过期而跳过。保持现有发现顺序，本次不以合并发现步骤作为优化前提。

同一用户轮内可复用本轮已经取得的有效目录；主模型多次推理、工具分批执行不自动构成新用户轮。目录结果不完整且影响匹配时按需补页，资源变化或相关执行失败时按需刷新；不得仅凭部分列表断言无匹配项。新用户轮须重新实际调用两个列表工具。

Skill 的加载与列表发现是不同步骤。匹配到并准备使用某个 Skill 时，本用户轮仍须通过 Skill 加载说明和动态参数，不得沿用上一用户轮的动态参数。

当前请求缺失时，先完成本轮双发现，再定向 recall 恢复当前请求；恢复前不执行猜测的业务任务。发现失败时按真实错误恢复，工具不可用时明确报告限制；不得使用上一轮结果伪称本轮发现成功。
```

Scroll 中的无条件“先恢复请求”相应改为“完成本轮强制发现后，业务执行前先恢复请求”，避免它与每轮发现前置冲突。不再提出跳过发现或在其之前 recall 的例外。

运行时已有目录、启动预加载或跨轮缓存均不能代替本轮实际调用。每轮发现的记录必须来自真实工具调用及其结果，不伪造调用完成状态。

### 3.3 SOUL 的替换段落

将中文默认模板中的“专业优先，流程强制，闭环交付”整段替换为：

```text
专业优先，流程统一，闭环交付。每个用户轮必须实际调用 list_agents 和 list_skills，再按 AGENTS.md 完成匹配及所需 Skill 加载；历史目录和缓存不能替代本轮发现。本文件不维护与 AGENTS 不同的发现顺序或省略条件。在所选执行路径中，遵循当前运行模式的工具提交规则；完成必要验证后及时交付，按复杂度评估是否需要复盘或建议沉淀为 Skill。
```

SOUL 保留人格、风格与主动性，不再独立维护另一套路由状态机。local、qa 等模板如有角色专属步骤，仍保留；共同运行规则由动态系统块提供。

### 3.4 Shell 工具描述与 guard 的职责分离

原子性文本建议替换为下面的等价英文版本，供工具描述、环境提示和 Shell guard 共用：

```text
Windows Non-Coding Mode: each execute_shell_command call must contain one self-contained, single-purpose process invocation. Do not compose shell commands using command separators, pipelines, redirection, or multiline command sequences. Do not hide independent operations inside interpreter code or a wrapper script. Pass the working directory through cwd; environment or directory changes in one call do not persist to another call. Prefer an available dedicated tool that covers the operation. A script implementing one task is allowed; atomicity means call granularity, not rollback.
```

另在面向主模型的工具描述中加入：

```text
One operation per call does not mean one call per assistant response. Once required prerequisites are satisfied, submit necessary independent inspection calls with fully known arguments in the same response. The runtime decides whether those calls can actually run concurrently. Wait for actual results before constructing dependent calls. Issue state-changing or uncertain shell operations one per response and wait for the result before proceeding. All permission rules still apply.
```

必须注意：

- Shell guard 只判断当前命令的路由和原子性，不为主模型规划后续批次。
- 增加一句 `allow_shell does not mean read-only, concurrency-safe, or authorized to bypass governance.`，避免将放行结论误用为并发凭证。
- 不把上面的主模型调度段整段塞进 guard；它看不到完整任务依赖，也不控制执行批次。
- 专用工具推荐必须根据当前实际可用工具决定。若某个专用工具当前不可见，不能仍固定返回一个模型无法调用的工具名；同时也不能因此放宽原本由权限策略禁止的操作。代码层的固定重定向检测与 guard 提示应一起检查。
- 不按字符串中出现任意分号就断言 Shell 链式调用。应结合实际 Shell 的引用和语法判断；单一任务脚本内部多条语句与多个独立任务不是同一概念。现有原子性校验仍保留，修改前先确认解析行为，不能仅通过改提示词扩大放行。

### 3.5 环境、Skill 与记忆提示的配套修正

将 `Skill Workflow Execution` 第 1 条改为：

```text
Before executing a selected skill, load its complete instructions and current-turn runtime parameters through Skill when that tool is available. Reading SKILL.md is only a fallback under the workspace's explicit Skill-loading fallback conditions; it does not provide missing current-turn dynamic parameters. Do not execute from a skill name or description alone.
```

顺序规则改为：

```text
Preserve the workflow's required order, branch conditions, validation and approvals. Satisfy prerequisites before dependent steps. Independent steps may be submitted together only when doing so is permitted by the workflow and does not change its meaning; explicitly ordered steps must remain ordered.
```

Skill 创建部分删除“不要求任何特定创建 Skill”这类与 AGENTS 相冲突的断言，替换为：

```text
This section defines skill ownership, file placement and registration. Follow any applicable user or workspace requirement for selecting or loading a creation skill. These path rules neither add nor remove such a requirement, and do not expand modification permissions.
```

Scroll 保留按需取回规则，并明确在本轮双发现完成后、业务执行前恢复缺失请求，不再保留发现前 recall 的例外。增加“历史只证明当时的记录，不证明外部当前状态”，不要求每轮自动 recall 或 memory_search。环境提示中无工具调用即完成的说法也应补充：等待用户或已运行后台任务时要明确状态；不应为保持任务进行而制造无意义工具调用。每轮强制的两个发现调用不属于可被这条精简规则省略的调用。

SOUL 的“每次会话从文件读取记忆”也建议明确为：“优先使用本会话已经提供的记忆；只有影响当前任务的必要信息缺失时才补读，不在每个用户轮重复读取记忆文件。”这项调整避免将会话初始化误解为逐轮工具前置，同时仍允许读取确有必要的记忆。

## 4. 运行时修改：提示词之外必须做什么

### 4.1 一份请求模式和能力快照

Builder 在工具构建前计算有效模式，工具过滤、CodingModeContributor、Windows 调度 Contributor、环境提示、Shell 原子规则和 FailureLoopGate 都使用这一份快照。Contributor 不再独立重新读盘推导另一份模式。

工具启停、Skill、权限过滤和 override 完成后，收集最终工具及真实能力。能力名单必须同时校验注册描述与实际工具实现，不能只凭名称信任插件或替换实现。通过同一份能力数据渲染提示词和安排调度。

对 `override.system_prompt` 明确分类：普通角色覆盖仍接受平台运行规则；若内部流程确实需要完整覆盖，必须使用显式的完整覆盖语义并有对应测试，运行时权限与并发约束仍不可绕过。不要悄悄改变所有 override 的含义。

### 4.1.1 每轮发现要求不能只依赖模型遵守

在项目的主 Agent 请求生命周期中，用 session、agent 与用户轮标识记录 list_agents / list_skills 的本轮调用及结果状态。不能以模型 iteration、上一用户轮状态或是否已知某个技能来代替用户轮边界。

在业务执行和完成判定前校验两项发现是否实际完成。漏调时通过原生工具调用流程纠正并留下真实结果，纠正次数要有界；发现失败、被拒绝或工具缺失时按实际原因恢复或明确报告受阻，不能伪造成功。只有部分分页时保留原有完整性与匹配规则。该校验用于面向用户请求的主 Agent 流程，不强迫 Shell guard 或 FailureLoopGate 内部审查模型调用它们未提供的列表工具。

这是一项运行时代码修改。提示词表达规则，代码负责发现漏调并防止直接进入业务执行或错误宣称完成；两者缺一不可。

### 4.2 先隔离权限状态，再放大并行

当前共享工具实例上存在逐次调用字段。至少需要隔离：原始参数、ToolCallSpec、策略决策、审批目标、执行路由、沙箱配置和请求上下文。

建议在每个原生工具调用生命周期开始时创建 `ToolCallScope`，用 ContextVar 管理，并在该 scope 内取得专属 PolicyGuardedTool 调用副本。SDK 的权限检查、审批等待、实际执行和后处理都访问同一个副本；结束时用 token 恢复上下文。共享 governor、不可变定义可复用，逐次调用的可变参数和审批状态不得共享。

只在执行函数里设置 ContextVar 不够：权限检查发生得更早；只加一个 command_id 字段也不能解决共享状态覆盖。包装器是否异步本身也不证明线程安全。

权限状态隔离应先覆盖同一个工具被并发调用的情况，例如两次 read_file、两次 Shell；不能只测试不同工具互不干扰。

当前直接执行分支已经保留工具原始 DENIED，不再把它一律当成沙箱失败去升级重试。这一点是需要保留并回归的现有行为，不应沿用旧方案中“仍未修复”的描述。

### 4.3 明确工具能力，不统一把所有工具设为 True

建议在 ToolDescriptor 补充独立字段，例如 `parallel_policy`，取值：`read_only`、`conditional_shell`、`barrier`。这与权限是否允许、是否后台执行、是否 async 是不同维度。

首批审核候选为当前实现的 `read_file`、`grep_search`、`glob_search`、`web_search`、`web_fetch`。入选前检查实际调用链：是否修改共享状态、是否使用共享浏览器会话、是否落盘、后台线程何时停止。HTTP GET、工具名带 read 或 SDK 的 readOnlyHint 均不能单独代替这一检查。

写文件、移动、删除、安装、浏览器/桌面控制、Skill 动态加载、未知插件默认作为执行屏障处理。Skill 是前置状态更新操作，不把它与依赖其动态参数的执行一起提交。

Shell 不整体归为 read_only。允许一组 Shell 查询同轮提交，不代表全部可以同时运行。第一版的硬并发名单可以先不包含 Shell；若这样会使当前已并行的版本检查明显变慢，则新调度开关不得直接上线，应先补调用级策略或保持原行为进行对照。

Shell 的后续调用级策略需要满足：受审的查询形态、可信且确定的可执行程序、确定的参数与执行上下文，且判定使用的执行目标与实际执行目标一致。不能只匹配 `--version` 字符串，更不能把任意 `python -c`、脚本名称、git 子命令或 LLM 的 allow_shell 当成确定只读证明。无法验证的调用串行处理；不要为了提速关闭原有语义门禁。

对经常出现的“环境信息查询”，还可以单独评估一个有明确输入输出、经过审查的环境检查工具；它是产品能力，不是在 Shell 脚本中包装独立命令绕过规则，不属于本次最低改动范围。

### 4.4 复用 SDK 执行链，限制实际运行数

当前 SDK 已经按连续的 concurrency_safe 调用分批，使用 gather 执行并发批次，并按 call ID 关联事件与结果。没有“只能两个工具”的固定限制，不重写 gather，也不直接改 `.venv`。

如果需要 Shell 调用级判断，在项目的 Agent 适配层集中实现分批判定，保留 SDK 的执行和事件机制。不能为了某次 Shell 调用临时修改共享工具的 `is_concurrency_safe`，否则又产生并发状态竞争。读取批次可并发，屏障调用保留原出现顺序，不把屏障后面的读取挪到它前面。

建议新增独立配置，以下名称与数值均为提案：

```json
{
  "windows_non_coding_parallel": {
    "enabled": false,
    "max_concurrent_per_session": 4,
    "max_concurrent_per_process": 8,
    "search_concurrency": 2,
    "network_concurrency": 3
  }
}
```

`enabled=false` 是新机制验证期间的部署默认值，验证通过后再启用，不表示关闭现有 SDK 并发。4/8 是初始试验值，不是测得的最优值。不要限制模型一轮只能发四条：八条独立查询可以在同一次回复中提交，由执行器分批处理，不必再多走一轮模型。

并发槽位必须涵盖实际工作生命周期。排队时间与执行时间分开记录；取消协程不代表 to_thread 的线程已停止；返回 pending 不代表后台任务完成；这些任务仍在占用资源时不得提前释放槽位。对已开始的实际执行仍要遵守原有超时；排队也不能无限等待，应受独立队列超时及总请求预算约束。

多层限制应由一个协调器统一获取或采用固定获取顺序，避免任务持有全局槽位却等待类别槽位形成资源占用或死锁。所谓进程上限是单进程运行时上限，多 worker 部署不会自动获得跨进程总上限。

这套调度不提供跨多个文件或外部系统的原子快照。若业务要求一致快照，应另用版本校验、快照或资源锁；不能从“几个读取并发成功”推出它们观察了同一时刻的状态。

### 4.5 不把 LLM 限流配置当工具并发开关

`running.llm_max_concurrent` / `llm_max_qpm` 限制的是模型调用，限流器通常按 provider:model 共享；同一模型的主对话、Shell 审查和复查可能互相等待。当前流式实现拿到首个 chunk 后释放模型槽位，所以该数值也不是整个输出期间的严格活跃流数量。

本方案不默认增大这些值。先记录模型槽位等待、429 退避及各阶段耗时，确认有额度再调。更大的工具批次可能同时产生更多 Shell 审查请求，反而增加 429。

不统一向所有 provider 注入 parallel_tool_calls=True。先验证当前实际模型路径是否正确传递多调用以及 provider 是否支持；日志已经能看到同轮两次 Shell，因此不能把所有多轮现象归因于 provider 不支持。必要的兼容修复单独进行协议边界测试。

已有 `shell_guard_disable_thinking` 仍只控制支持的在线模型的 Shell 审查请求；值为 0 表示保持原模型配置，值为 1 表示请求关闭支持的在线模型 thinking。本次核对发现当前 `main.py` 的无环境覆盖默认值已经是 1，提示词阶段未修改该设置。三个指定本地模型继续保留原策略。它不会自动减少主模型轮数，也不会改变 FailureLoopGate 的启用和复查周期。

## 5. 用真实场景检查依赖关系

| 场景 | 应如何提交 | 不应怎样做 |
| --- | --- | --- |
| 每个用户请求，包括轻量回应 | list_agents → list_skills → 匹配 → 按需 Skill 加载 → 查询或回答 | 省略任意一个发现调用；发现未完成就开展业务查询 |
| 后续请求，上一轮列表仍可见 | 仍实际调用两个列表工具，按本轮结果匹配 | 用历史目录、启动预加载或缓存替代本轮调用；沿用上一用户轮 Skill 动态参数 |
| 同一请求内继续多个模型轮 | 复用本用户轮有效的发现结果，必要时补页或刷新 | 把每次模型推理都当新用户轮，重复执行双发现 |
| 用户明确给两份已授权文件 | 路径已知，完成前置后，两次 read_file 可同轮提交 | 为读取已知路径先额外搜索；把读权限视为改权限 |
| 不知道某份报告在哪 | 按挂载优先级定位 → 根据结果读取 | 猜出一个路径与搜索调用同时读取；跨根无序扩大搜索 |
| 搜索两组独立信息 | 参数已知、范围有授权时，两次查询同轮发出 | 第二组查询用尚未返回的第一组 URL 或关键词 |
| Python 环境查询 | 按目标选择必要的版本、解释器位置或可用版本查询；具备条件的调用同轮提交 | 默认把 pip、所有版本、某个假定的 Python3.11 都检查一遍 |
| 安装后验证 | 安装得到真实结果后，再验证安装结果 | 安装和版本验证同时发出 |
| 搜索 → 读 → 改 → 验证 | 按结果依赖逐阶段推进；阶段内独立读取可合并 | 以串行执行为由，在同一回复中预填尚未知的编辑内容 |
| 同一浏览器页面 | 保持导航、点击、截图的状态顺序 | 将两个“看起来只读”的页面动作认定无共享状态 |
| 后台长任务 | 按后台工具实际结果状态查询与回收 | 将 pending 当成完成，然后执行依赖操作或报成功 |

以原来的 Python 查询组为例，在每轮双发现约束下，默认 Agent 且无额外 Skill 加载/协作前置时，可以争取下面的目标链。为公平对照，改造前后的基线都保留双发现；原历史日志未调用 list_skills，不能直接声称它已经满足最新要求：

```text
同约束基线：list_agents → list_skills → 查询组1 → 查询组2 → 查询组3 → 总结
目标：      list_agents → list_skills → 已知且必要的独立查询组 → 总结
```

这只是满足前提时的目标，不保证所有模型和任务固定轮数，也不再以省去 list_agents 或 list_skills 计算收益。若用户只问 Python 版本，通常也不需要执行原来全部六个检查。`where.exe python`、`python --version`、`py -0p` 可作为按需选择的查询示例；它们是否能实际并发还取决于上述调用级策略、默认 Shell 和解释器来源。若任务需要指定版本、pip 或架构信息，再根据目标与已取得结果补查。

不能用原日志中全部 Shell 审查时间相加来估算用户等待：同组内并行等待主要由最长路径决定。将多轮压成一轮后，收益也受到模型时延、审查并发、执行限制、重试和必要前置的影响，应测量而非承诺固定倍数。

## 6. 拟改文件和实施顺序

| 文件 | 主要修改 |
| --- | --- |
| 新增 `config/tool_dispatch_policy.py` | 共用提示文本、调度能力类型和只读规则定义；避免多份不一致文案 |
| `runtime/builder.py` | 有效模式快照、最终能力收集、override 语义接入 |
| `runtime/prompt_contributors.py` | 新增 Windows 非 Coding Contributor；Coding 提示读取有效模式 |
| `agents/md_files/zh/AGENTS.md`、`SOUL.md`，必要的对应语言 | 统一每用户轮双发现；删除跨用户轮省略列表调用的条款；普通工具并发不自动升级协作 |
| `app/chats/utils.py` | 原子提示来源统一；Skill 加载、创建与完成状态文案消除冲突；保留路径规则 |
| `config/shell_policy.py`、`agents/tools/shell.py` | 原子调用与同轮提交分离；guard 不声称授予并发权限；检查专用工具推荐的可见性 |
| `runtime/tool_registry.py`、`app/workspace/local_workspace.py` | 明确审核过的能力，并传给运行时；保守处理未知工具 |
| `governance/tool_adapter.py` | 每个调用的权限、参数与审批状态隔离；原拒绝语义保持 |
| `agents/react_agent.py` 及项目内调度适配模块 | 每用户轮双发现状态与执行校验；原生调用生命周期 scope、批次策略和实际执行计时；保留事件与 call ID |
| 后台/搜索执行路径，按实际需要 | 槽位跟踪至真实线程或后台任务结束，处理取消和超时 |
| 配置 schema、`main.py` | 独立并发开关与生效日志；提示模板同步核对；不复用 thinking 开关 |

推荐顺序：

1. 先固定每用户轮双发现要求、用户轮边界、有效模式和回归场景，完成权限状态隔离。
2. 合并提示词冲突，加入每轮发现校验与同轮业务查询提交规则，保留现有执行机制做同约束基线对照。
3. 接入明确能力、运行时限制和线程/后台生命周期；Shell 调用级策略单独审查，不把已允许执行直接当并发资格。
4. 先验证普通读取/搜索，再验证 Shell 场景；若 Shell 串行化使关键场景退化，继续保持新开关关闭，补齐策略后再启用。
5. 通过真实模型对照后再部署，观察主模型、门禁与工具的分段耗时。

启动时 `main.py::_sync_default_prompt_files` 当前会把源码语言模板的 AGENTS、SOUL 同步到 default 工作区。因此应改源码模板并检查重新打包后的产物，不能只改 paw-runtime 下的运行文件。其他 Agent、local/qa 模板与用户定制提示不能一律覆盖。新 Contributor 要在新构建时生效；若复用已有 Agent 实例，还要明确重建或提示版本失效机制。

## 7. 打印哪些内容才能判断是否有效

保留已经加入的 MainModel 与 FailureLoopGate 分段日志，再增加下列结构化事件：

```text
ToolDispatch session=... reply=... iteration=... batch=... submitted=4 parallel_eligible=3 barrier_count=1 policy_version=...
ToolTiming call_id=... tool=read_file phase=queued queue_ms=...
ToolTiming call_id=... tool=read_file phase=permission permission_ms=... decision=allow
ShellGuardTiming call_id=... phase=review model_ms=... thinking_mode=disabled retry_count=...
ToolTiming call_id=... tool=read_file phase=execution execution_ms=... state=success
ToolTiming call_id=... phase=background_pending actual_running=true
```

这是拟新增格式，不代表当前所有字段都已存在。记录工具名、调用 ID、阶段、时长、状态、策略版本及有限的分类原因即可；不要重复打印完整命令、用户参数、文件正文、审批秘密或模型输入。对原因使用类别而非自由转储数据。

重点比较：主模型调用次数及首个实际输出等待；主模型与门禁分别花多久；同轮提交数量；实际同时执行数；权限和并发队列等待；Shell 审查等待及 thinking 模式；429/502 和重试；端到端耗时；非必要调用数量。

同时记录模式快照、prompt/策略版本或哈希、各提示来源字符数、工具数量和 API 返回的实际输入 token；字符数和估算 token 不能冒充 API usage。Agent 构建中的环境检测也单独计时：若运行时已提供仍适用的确定性信息，模型不应再机械探测；若要缓存环境检测，应有明确的作用域和失效条件，不能把过期版本当成现状。

FailureLoopGate 默认是否启用、是否到复查间隔，直接看配置与 skipped/review 日志。缩短主模型轮数可能减少到达复查阈值的机会，但不是通过关 gate 来获得提速。SSE 建连成功和收到 HTTP 200 不表示模型已经开始输出。

## 8. 验收与回退条件

自动化测试至少覆盖：

- Windows 非 Coding 与 Coding/Linux/macOS 的注入边界；enabled 但 project_dir 缺失的有效模式一致性。
- 工具被禁用、替换或 override 后，提示中的能力与真实工具表一致。
- 每个用户轮都实际调用 list_agents 和 list_skills；历史可见、缓存命中、轻量请求均不导致省略；同用户轮多次模型推理不机械重复。
- 漏调、发现失败、工具不可用、分页和用户轮切换时状态正确；完成判定不会绕过本轮发现；内部门禁审查不误套主 Agent 的发现要求。
- 两次同名工具交错执行时，参数、允许/拒绝决定、审批目标和上下文无串用；审批 A 不能放行 B。
- 独立读取可同批；读取、写屏障、后续读取不被重排；未知和不透明 Shell 不因名称自动并发。
- call ID、工具事件和结果一一对应；部分失败不丢其他结果、不无差别重试全部调用。
- pending、线程取消、后台完成、队列超时与请求预算下槽位不提前释放或泄漏。
- 权限拒绝、只读挂载、Windows 大小写/混合分隔符、junction、默认输出根等原规则保持。
- 在线 Shell thinking 的既有协议测试和三个本地模型保留规则继续通过。

真实模型做相同场景的多次 A/B 对照，覆盖实际 provider；本地模型的角色提示与在线模型不同，应分别统计。固定输入、有效工具、初始目录/缓存状态与配额条件，交替运行，避免把模型服务波动当提示收益。建议每场景至少五次，样本较小时主要看原始分布和中位数，不把极小样本的 p95 当稳定结论。

必须同时检查正确率、遗漏必要步骤、越权、无关调用和耗时。离线 mock 能验证调度与权限机制，不能证明模型会更积极地产生同轮多调用；模型对照也不能替代权限交错测试。

出现权限状态串用、依赖被跨越、结果错配或实际运行数超过限制时，停止新调度灰度；出现明显延迟回退时检查 Shell 串行化、排队和 429，再调整能力与上限。回退新功能时保留独立可验证的权限状态隔离修复和诊断日志，不用恢复整个工作区的方式撤销其他改动。

## 9. 预期结果与不能承诺的部分

本方案保留每个用户轮必须执行的 list_agents 和 list_skills，主要减少其后的独立业务查询往返和不必要的业务检查，再使同轮调用的实际并发可控、可观测。它不会自动降低主模型单次生成时间，也不能消除网关 502、模型服务排队、必须等待的发现/Skill/路由步骤或用户审批。

完整的后续设计还包括每用户轮双发现状态和校验、有效模式一致、每次调用权限隔离、执行计时及受开关控制的调度改造。根据用户最新决定，本次只落地提示词与对应渲染接入，先观察模型提交行为；上述运行时代码留待后续，不以提示词阶段已完成来声称这些机制已实现。
