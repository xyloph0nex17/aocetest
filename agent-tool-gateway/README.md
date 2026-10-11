# Agent 工具调用安全网关

这个项目用固定 JSON 模拟 Agent 提出的工具调用。Client 将调用提交给 Gateway；Gateway 根据服务端保存的工具定义、参数 Schema 和路径规则，决定直接执行、等待用户确认或拒绝。`send_email` 只在本地写入 JSON 文件，不连接真实邮件服务。

## 环境与启动

以下命令在项目目录 `agent-tool-gateway` 中运行。需要 Python 3.10 或更新版本。Windows PowerShell 可以直接调用虚拟环境中的 Python，无需激活虚拟环境。

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install fastapi uvicorn requests jsonschema
```

在第一个终端启动 Gateway：

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

在第二个终端运行 Client。它默认读取 `client/read_note_call.json`，也可以指定其他调用文件：

```powershell
.\.venv\Scripts\python.exe -m client.main .\client\read_note_call.json
.\.venv\Scripts\python.exe -m client.main .\client\email_call.json
.\.venv\Scripts\python.exe -m client.main .\client\delete_call.json
```

`email_call.json` 会触发确认提示。输入 `approve` 才会在 `sandbox/outbox/` 中生成邮件 JSON；输入其他内容会拒绝。当前 `delete_call.json` 使用 `../../config.json`，用于演示越界路径被拒绝，不会提示确认。若要演示合法删除，请先在 `sandbox/notes/` 中创建一个临时文件，再将调用文件中的 `path` 改为该文件名；确认后该文件会被删除。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

现有测试检查：合法读取、邮件确认前无副作用、用户拒绝后无副作用、同一确认只能执行一次、并发确认仅执行一次、确认过期、身份和参数绑定、未知工具与非法参数拒绝、路径越界拒绝，以及批准和拒绝的审计记录。大部分测试直接调用 Gateway 的处理函数；审计测试调用接口函数，上面的 Client 命令用于演示完整的 HTTP 交互。

## 设计与职责

| 部分 | 职责 |
| --- | --- |
| `client/` | 读取模拟 Agent 输出的 ToolCall，发送请求，展示执行结果或拒绝原因；遇到待确认调用时，展示工具名和完整参数，并按用户输入提交确认或拒绝。 |
| `server/gateway/registry.py` | 保存可信的工具 Schema 和风险策略。`read_note` 可以直接执行，`send_email` 与 `delete_note` 需要确认。 |
| `server/gateway/validator.py` | 校验 ToolCall、参数格式和笔记路径是否处于 `sandbox/notes/` 内。 |
| `server/gateway/service.py` | 根据校验结果返回 `allow`、`require_approval` 或 `deny`，并在适当时机执行工具。 |
| `server/gateway/approvals.py` | 暂存待确认调用及其用户身份、参数摘要、有效期；使用锁和 `used` 标记，使同一个 `approval_id` 在当前服务进程内只能使用一次。 |
| `server/tools/` | 读取笔记、删除笔记，或将模拟邮件写入 `sandbox/outbox/`。 |
| `server/app.py`、`server/gateway/audit.py` | 提供 HTTP 接口，并将请求决定和审批结果追加到 `sandbox/audit.jsonl`。 |

Client 向 `POST /tool-calls` 提交包含 `call_id`、`tool_name` 和 `arguments` 的 JSON，并在 `X-User-Id` 请求头中附上模拟用户身份。只读且合法的调用直接执行；高风险调用返回 `approval_id`，此时不执行工具。用户作出选择后，Client 向 `POST /approvals/{approval_id}/decision` 提交 `action`、原 `call_id`、`tool_name` 和 `arguments`，并再次附上相同的 `X-User-Id`。Gateway 核对身份与调用内容、检查有效期和使用状态，通过后才可能执行工具。

审计文件 `sandbox/audit.jsonl` 每行是一条 JSON 记录，包含时间、调用或审批事件、决定、状态，以及存在时的 `approval_id` 和执行结果。运行时生成的邮件和审计文件不提交到 Git。

## 任务书问题

### Client 和 Gateway Server 分别负责什么？
Client 读取模拟 Agent 提出的工具调用，发送给 Gateway，并向用户展示结果、请求用户确认，再把用户实际选择的批准或拒绝发送给 Gateway。
Gateway 保存可信的工具定义和风险策略，负责校验、决定是否执行、管理确认记录、执行工具及写入审计日志。

### 为什么 Agent 输出不能被视为用户授权？
Agent的输出不等于用户就一定想这么做

### 为什么确认必须绑定具体参数，而不能只绑定工具名称？
因为可能调用工具是合法的，但被篡改了工具的参数导致最终调用不合法

### 为什么工具的风险策略必须保存在 Gateway，而不能由 Agent 提交？
如果让agent掌握，他可能将一个高风险操作注明为低风险从而绕过检查

### 如果一次工具执行超时，系统如何判断它能否安全重试？
超时只说明 Client 没收到结果，不说明工具没有执行。 read_note 没有副作用，通常可以重试；发送邮件、删除文件则必须先查执行记录或实际结果，不能直接重试。

## 当前范围

当前完成了除challenge以外的基础与进阶部分
