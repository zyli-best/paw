# 普通 Console 任务引导

本文描述普通模式。云边端协同现已使用独立实现支持引导，语义见 [云边端协同引导](edge-cloud-steering.md)，接口参数相同。

完整的字段说明、错误码和调用流程见 [Steer 接口与调用逻辑](steering-api.md)，可复用的 JavaScript 调用示例见 [steer-client.mjs](examples/steer-client.mjs)。

仅在本次请求的有效云边端协同配置关闭、且启动任务时显式提供客户端 `run_id` 时启用。启用协同但回退普通执行的任务也不启用。未提供 `run_id` 的旧客户端保持原有流程，可以查询任务存在和运行状态，但不能 steer。

## 启动任务

沿用 `POST /api/console/chat`，在现有请求顶层增加可选字段：

```json
{
  "session_id": "原有会话标识",
  "user_id": "原有用户标识",
  "run_id": "5f576e5a-4726-4fbb-a532-5f43af8dd17b",
  "input": [{"role": "user", "content": [{"type": "text", "text": "完成任务"}]}],
  "stream": true
}
```

`run_id` 由客户端生成，每次新任务使用新的 UUID；服务端不补生成、不替换。服务端接受长度不超过 128 的非空字符串，唯一性由调用方保证。重连沿用现有 `reconnect` 流程，不会修改活动任务身份，也不会补开 steer 能力。重复启动请求仍沿用原有 attach 行为，不把新的 `run_id` 覆盖到活动任务。

Console 前端在启动请求中自动生成 UUID；运行时输入消息沿用现有队列，点击队列里的“引导当前任务”提交文本引导，不自动改变普通发送行为。文件引导暂不支持。

## 查询当前状态

`GET /api/console/chat/status?chat_id=<ChatSpec.id>`，通过现有 `X-Agent-Id` 选择工作区。查询参数不需要 `run_id`。这里的 `chat_id` 是服务端聊天记录 ID，可能不同于启动请求的 `session_id`。

支持引导的活动任务：

```json
{
  "agent_id": "default",
  "chat_id": "聊天记录ID",
  "exists": true,
  "status": "running",
  "run_id": "5f576e5a-4726-4fbb-a532-5f43af8dd17b",
  "can_steer": true
}
```

旧客户端启动的任务运行时返回 `exists: true`、`status: "running"`、`run_id: null`、`can_steer: false`。任务构建中或收尾时也可能不能接收引导。任务结束后返回 `exists: false`、`status: "idle"`、`run_id: null`、`can_steer: false`。`exists` 表示活动任务存在；聊天记录不存在时返回 404。

状态是瞬时快照；提交时仍需校验身份。不能根据一次状态查询保证随后的提交一定被接收。

## 提交引导

`POST /api/console/chat/steer`，工作区头与查询保持一致：

```json
{
  "chat_id": "聊天记录ID",
  "run_id": "5f576e5a-4726-4fbb-a532-5f43af8dd17b",
  "message_id": "客户端为本条引导生成的UUID",
  "text": "请改用 D 盘中的配置文件"
}
```

首次接收返回 202，重复请求返回 200，响应包含 `run_id`、`message_id`、`sequence` 和 `status`。`queued` 表示已入队，`injected` 表示已写入上下文；接收成功不代表模型已执行。每个任务最多接收 128 条不同 ID 的引导，每条文本最多 16000 字符。

同一任务内，相同 `message_id` 和相同文本返回原记录，不重复插入；相同 ID 不同文本返回 409 `MESSAGE_ID_CONFLICT`。不同 ID 按接收顺序注入。任务不支持引导、已经结束、正在收尾或 `run_id` 不匹配均拒绝，不新建任务、不转投下一轮。任务启动、重连的幂等行为继续沿用原有机制；此处新增的是引导提交的幂等。

客户端遇到网络超时后，必须使用第一次提交时保存的 `agent_id/chat_id/run_id/message_id/text` 重试。Console 队列会持久化这些身份，刷新后不会自动改投下一轮，也不会将失败的引导自动当作普通新任务发送。

## 注入与压缩

工具执行期间仅入队，不打断工具；当前工具批次结束后，在下一次 Scroll 压缩前取队列快照、经现有脱敏流程处理，再追加原生 `user` 消息。快照之后新到的引导在后续边界处理；最终一次推理期间到达的引导可触发同一任务的下一次推理，仍受已有迭代限制和停止门禁约束。

发生过引导后，Scroll 从本次原始任务开始保护活动上下文，保护原始输入和所有已注入引导。已有历史裁剪和工具结果折叠继续使用原流程。请求发送前再次核验输入 ID；如压缩无法保留，显式报错，避免静默丢失引导。未发生注入时，Scroll 保持原有逻辑。

## 生命周期与 Langfuse

排队信息、幂等回执和注入状态只存当前活动任务内存，完成、失败或停止后随现有 TaskTracker 清理，不保留十分钟缓存，不支持结束后的回执查询或跨服务重启幂等。结束前未写入上下文的输入标记为 `not_applied`；已写入的输入随现有会话持久化。

普通任务继续使用现有 session delta 上传。注入消息携带 `agent_id`、`chat_id`、`run_id`、内部 `response_id`、`message_id`、序号、接收和注入时间。对发生引导的任务按加载时的消息 ID 排除旧历史，避免 Scroll 改变长度后漏传。停止或异常时先构建独立快照，复用现有异步上传器，每个任务至多调度一次。只上传已写入上下文的引导，不把未应用的队列文本混进模型对话。云边端上传结构和导出器不变；网络上传可靠性沿用现有上传器。
