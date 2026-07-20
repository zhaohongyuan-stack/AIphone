# API 契约文档（DB 同事协作参考）

> 本文档描述 IVR 智能语音工单系统的所有 API 端点、数据库表结构、Redis 键约定，
> 供 DB 同事在编写数据库操作脚本时参考。所有接口均以 `POST/GET/PUT` 方式调用，
> 返回统一格式 `{ "code": 200, "data": {...} }`。

---

## 一、协作流程

### 角色分工

| 角色 | 职责 | 工具 |
|------|------|------|
| **后端开发（你）** | 运行 pytest 测试，驱动全链路 | `tests/` 目录下的测试脚本 |
| **DB 同事** | 数据库初始化、验证、导出 | `database/` 目录下的脚本 |
| **共享工具** | 测试辅助函数 | `tests/helpers.py` |

### 测试执行顺序

```
# 1. DB 同事：初始化测试数据
python -m database.seed_data

# 2. 后端开发：运行分块测试（按顺序）
pytest tests/test_ivr_routing.py -v          # 块1: IVR 分流
pytest tests/test_robot_dialogue.py -v       # 块2: 智能对话机器人
pytest tests/test_redis_queue.py -v          # 块3: Redis 排队队列
pytest tests/test_integration_e2e.py -v      # 块4: 端到端集成

# 3. DB 同事：验证数据正确性
python -m database.verify_data

# 4. DB 同事：导出测试数据（可选上传 OSS）
python -m database.export_test_data --upload

# 5. 后端开发：运行 OSS 上传测试
pytest tests/test_oss_uploader.py -v
```

### DB 同事如何参与全链路

DB 同事有两种方式参与：

1. **直接调用 API**（推荐）：通过 `tests/helpers.py` 中的辅助函数，使用 `httpx` 调用正在运行的服务
2. **直接操作数据库**：通过 `database/` 下的脚本，使用 SQLAlchemy 直接读写 PostgreSQL

---

## 二、API 端点列表

### 2.1 工单接口

#### `POST /api/orders` — 创建工单（存入 work_order 表）

IVR 阶段创建空工单（用户拨入电话后立即调用）。

**请求体：**
```json
{
  "phone": "13800138000",
  "conversation_id": "conv-xxx-yyy",
  "instance_id": "ccc-test-instance",
  "order_type": 1
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| phone | string | 是 | 来电号码 |
| conversation_id | string | 是 | CCC 会话 ID |
| instance_id | string | 是 | 热线机器人实例 ID |
| order_type | int | 否 | 工单类型：0-转播 1-咨询 2-投诉 3-回访（默认1） |

**响应：**
```json
{
  "code": 200,
  "data": { "order_id": 1 }
}
```

---

#### `GET /api/orders/{order_id}` — 获取工单详情

坐席弹屏用，附带历史对话。

**响应：**
```json
{
  "code": 200,
  "data": {
    "order_id": 1,
    "phone": "13800138000",
    "conversation_id": "conv-xxx",
    "ent_name": "某某科技有限公司",
    "ent_address": "杭州市西湖区...",
    "ent_cerdit": "91XXXX...",
    "contact_name": "张三",
    "order_type": 1,
    "order_status": 1,
    "agent_id": null,
    "biz_summary": "咨询营业执照办理流程",
    "ai_solved": 0,
    "ai_failure_note": null,
    "call_start_time": "2026-07-08T10:00:00",
    "history": [
      { "role": "user", "content": "...", "time": "10:00:05" },
      { "role": "bot", "content": "...", "time": "10:00:06" }
    ]
  }
}
```

---

#### `PUT /api/orders/{order_id}` — 更新工单

理解 Skill 提取后 / 坐席填写后更新工单字段。

**请求体（所有字段可选）：**
```json
{
  "ent_name": "某某科技有限公司",
  "ent_address": "杭州市西湖区...",
  "ent_cerdit": "91XXXX...",
  "contact_name": "张三",
  "order_type": 1,
  "order_status": 2,
  "agent_id": 1,
  "biz_summary": "咨询营业执照办理流程",
  "ai_failure_note": null,
  "ai_solved": 1,
  "summary_confirmed": 0
}
```

**响应：**
```json
{ "code": 200, "message": "更新成功" }
```

---

#### `GET /api/orders/by-phone/{phone}` — 根据电话查历史工单

根据来电号码查询该用户的历史工单列表，返回**完整工单字段**（不含对话历史）。

**用途：** 人工坐席接单后，前端额外调用此接口获取当前用户的历史工单，
在坐席前端展示该用户的历史咨询/投诉记录，便于人工客服快速了解用户背景。

> 注意：返回完整工单字段，但 **不包含** 对话历史（history）。
> 如需对话详情，请单独调用 `GET /api/orders/{order_id}`。

**响应：**
```json
{
  "code": 200,
  "data": [
    {
      "order_id": 1,
      "phone": "13800138000",
      "conversation_id": "conv-xxx",
      "instance_id": "ccc-test-instance",
      "ent_name": "某某科技有限公司",
      "ent_address": "杭州市西湖区...",
      "ent_cerdit": "91XXXX...",
      "contact_name": "张三",
      "order_type": 1,
      "order_status": 2,
      "agent_id": 1,
      "biz_summary": "咨询营业执照办理流程",
      "ai_solved": 1,
      "ai_failure_note": null,
      "call_start_time": "2026-07-08T10:00:00",
      "call_end_time": "2026-07-08T10:05:00",
      "created_time": "2026-07-08T10:00:00",
      "update_time": "2026-07-08T10:05:00"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| order_id | int | 工单 ID |
| phone | string | 来电号码 |
| conversation_id | string | CCC 会话 ID |
| instance_id | string | 热线机器人实例 ID |
| ent_name | string/null | 企业名称 |
| ent_address | string/null | 经营地址 |
| ent_cerdit | string/null | 统一社会信用代码 |
| contact_name | string/null | 联系人姓名 |
| order_type | int | 工单类型：0-转播 1-咨询 2-投诉 3-回访 |
| order_status | int | 工单状态：0-主动挂断 1-处理中 2-已办结 3-待回访 4-排队中 5-振铃中 |
| agent_id | int/null | 受理坐席 ID |
| biz_summary | string/null | 业务诉求摘要 |
| ai_solved | int | AI 是否解决：0-否 1-是 |
| ai_failure_note | string/null | AI 未解决问题记录 |
| call_start_time | string/null | 通话开始时间（ISO 格式） |
| call_end_time | string/null | 通话结束时间（ISO 格式） |
| created_time | string/null | 工单创建时间（ISO 格式） |
| update_time | string/null | 最后更新时间（ISO 格式） |

> 默认返回最近 20 条工单，按创建时间倒序排列。

---

#### `POST /api/orders/{order_id}/dispatch` — 工单完结流转推送

将工单标记为已办结，推送到后端处理人员系统。

**请求体：**
```json
{ "receiver": "backend_processor" }
```

**响应：**
```json
{ "code": 200, "data": { "order_id": 1, "order_status": 2 } }
```

---

### 2.2 智能坐席槽位接口

#### `GET /api/robot-slots/status` — 获取所有槽位状态

**响应：**
```json
{
  "code": 200,
  "data": [
    {
      "slot_id": 1,
      "status": "busy",
      "order_id": 1,
      "session_id": "uuid-xxx",
      "started_at": 1720000000.0,
      "duration_seconds": 120
    },
    {
      "slot_id": 2,
      "status": "idle",
      "order_id": null,
      "session_id": null,
      "started_at": null
    }
  ]
}
```

---

#### `POST /api/robot-slots/assign` — 分配智能坐席槽位

**查询参数：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_id | int | 是 | 工单 ID |
| phone | string | 是 | 来电号码 |

**响应（有空闲槽位）：**
```json
{
  "code": 200,
  "data": { "slot_id": 1, "status": "busy", "session_id": "uuid-xxx" }
}
```

**响应（槽位已满，入队等待）：**
```json
{
  "code": 200,
  "data": { "slot_id": null, "queued": true, "queue_position": 3 }
}
```

---

#### `POST /api/robot-slots/{slot_id}/release` — 释放槽位

挂断或转人工后释放槽位，自动从队列中取出下一个等待的工单。

**响应：**
```json
{
  "code": 200,
  "data": { "slot_id": 1, "status": "idle", "next_order_id": 5 }
}
```

---

### 2.3 智能对话接口

#### `POST /api/robot/dialogue` — 机器人对话

核心对话接口，处理一轮用户输入：
1. 记录用户输入到历史对话 + 数据库
2. 检查"拒绝解答"关键词
3. 调用 Beebot SSE 对话（携带历史对话 JSON）
4. 检查转人工指令（sysToAgent）
5. 理解 Skill 提取结构化信息并更新工单
6. 填写 Skill 追问缺失字段

**请求体：**
```json
{
  "order_id": 1,
  "utterance": "我想咨询一下营业执照怎么办理"
}
```

**响应（正常回答）：**
```json
{
  "code": 200,
  "data": {
    "action": "answer",
    "answer": "您好，营业执照办理需要...",
    "follow_up": "请问您能提供一下企业名称吗？"
  }
}
```

**响应（转人工）：**
```json
{
  "code": 200,
  "data": {
    "action": "transfer_to_agent",
    "answer": "正在为您转接人工客服...",
    "reason": "机器人转人工: 用户要求"
  }
}
```

**响应（拒绝解答）：**
```json
{
  "code": 200,
  "data": {
    "action": "transfer_to_agent",
    "reason": "拒绝解答",
    "reject_item": {
      "question": "医疗纠纷",
      "answer": "超出业务范围",
      "group": "拒绝解答"
    }
  }
}
```

---

#### `GET /api/dialogue/stream/{order_id}` — SSE 流式对话

Server-Sent Events 流式返回机器人对话内容。

**响应：** `text/event-stream`

```
data: {"content": "您好", "done": false}
data: {"content": "，请问", "done": false}
data: {"content": "有什么可以帮您？", "done": true}
```

---

### 2.4 人工坐席接口

#### `GET /api/agents` — 获取所有坐席列表

**响应：**
```json
{
  "code": 200,
  "data": [
    {
      "agent_id": 1,
      "agent_name": "测试坐席A",
      "agent_status": 1,
      "ccc_agent_id": "agent_a@ccc-test",
      "skill_group_id": "sg_business"
    }
  ]
}
```

---

#### `GET /api/agents/status` — 获取坐席状态（含 Redis 缓存）

---

#### `PUT /api/agent/status` — 更新坐席状态

**请求体：**
```json
{
  "agent_id": 1,
  "agent_status": 1,
  "ccc_agent_id": "agent_a@ccc-test",
  "skill_group_id": "sg_business",
  "device_id": "device-xxx"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_id | int | 是 | 坐席 ID |
| agent_status | int | 是 | 0-离线 1-忙碌 2-在线 |
| ccc_agent_id | string | 否 | CCC 坐席 ID |
| device_id | string | 否 | 设备 ID |

---

#### `POST /api/agent/accept` — 人工坐席接单

人工坐席从队列取出下一个工单并接单。返回**当前工单的完整字段**（不含对话历史），
前端拿到 `phone` 后可额外调用 `GET /api/orders/by-phone/{phone}` 获取该用户的历史工单列表。

**请求体：**
```json
{
  "agent_id": 1,
  "order_id": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| agent_id | int | 是 | 坐席 ID |
| order_id | int | 否 | 指定工单 ID（队列为空时兜底，不传则从队列取下一个） |

**响应：**
```json
{
  "code": 200,
  "message": "接单成功",
  "data": {
    "order_id": 1,
    "phone": "13800138000",
    "conversation_id": "conv-xxx",
    "instance_id": "ccc-test-instance",
    "ent_name": "某某科技有限公司",
    "ent_address": "杭州市西湖区...",
    "ent_cerdit": "91XXXX...",
    "contact_name": "张三",
    "order_type": 1,
    "order_status": 1,
    "agent_id": 1,
    "biz_summary": null,
    "ai_solved": 0,
    "ai_failure_note": "AI 摘要：用户咨询营业执照办理...",
    "call_start_time": "2026-07-08T10:00:00",
    "call_end_time": null,
    "created_time": "2026-07-08T10:00:00",
    "update_time": "2026-07-08T10:00:00"
  }
}
```

> **前端建议流程：**
> 1. 调用本接口接单，拿到当前工单完整字段（含 `phone`）
> 2. 用 `phone` 调用 `GET /api/orders/by-phone/{phone}` 获取历史工单列表
> 3. 左侧展示当前工单（随交互逐渐填写），右侧展示历史工单（只读）

---

### 2.5 CCC 事件回调

#### `POST /api/ccc/callback` — CCC 事件回调

接收阿里云 CCC 推送的事件（测试时由 mock 发送）。

**请求体（CallStarted）：**
```json
{
  "EventType": "CallStarted",
  "ConversationId": "conv-xxx",
  "Caller": "13800138000",
  "InstanceId": "ccc-test-instance"
}
```

**请求体（IvrKeyPressed）：**
```json
{
  "EventType": "IvrKeyPressed",
  "ConversationId": "conv-xxx",
  "Key": "1"
}
```

| 按键 | 含义 | 触发动作 |
|------|------|----------|
| 1 | 企业咨询 | 创建工单(type=1) + 分配槽位 + Bot 对话 |
| 2 | 投诉 | 创建工单(type=2) + 分配槽位 + Bot 对话 |
| 0 | 转人工 | 创建工单(type=0) + 直接转人工坐席 |

**请求体（CallHangup）：**
```json
{
  "EventType": "CallHangup",
  "ConversationId": "conv-xxx",
  "HangupDir": "User"
}
```

**请求体（AsrResult）：**
```json
{
  "EventType": "AsrResult",
  "ConversationId": "conv-xxx",
  "Content": "语音转写文本"
}
```

---

### 2.8 质检模块

#### `GET /api/quality-inspection/orders` — 获取质检工单列表

按日期筛选工单，返回每个工单的对话数、已评价数和质检状态。

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 是 | 日期 YYYY-MM-DD，按 call_start_time 筛选 |
| order_type | int | 否 | 工单类型：0-转播 1-咨询 2-投诉 3-回访 |
| inspection_status | int | 否 | 质检状态：0-全部待评价 1-部分已评价 2-全部已评价 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |

**响应：**
```json
{
  "code": 200,
  "data": {
    "total": 45,
    "page": 1,
    "page_size": 20,
    "orders": [
      {
        "order_id": 1,
        "phone": "138****8000",
        "order_type": 1,
        "order_status": 2,
        "ent_name": "某某科技有限公司",
        "agent_id": 1,
        "call_start_time": "2026-07-18T09:30:00",
        "call_end_time": "2026-07-18T09:38:00",
        "dialogue_count": 12,
        "evaluated_count": 0,
        "inspection_status": 0
      }
    ]
  }
}
```

| 返回字段 | 类型 | 说明 |
|----------|------|------|
| dialogue_count | int | 该工单对话总条数 |
| evaluated_count | int | 已评价条数 |
| inspection_status | int | 0-全部待评价 / 1-部分已评价 / 2-全部已评价 |

#### `GET /api/quality-inspection/orders/{order_id}/dialogues` — 获取工单对话记录（含评价）

首次访问时，系统自动从 `dialogue_detail` 表拉取该工单所有对话，将 `content`、`role`、`msg_time` 组装为 JSON 写入 `quality_inspection` 表（`evaluation` 为空），然后返回。后续访问直接返回已有质检记录。

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_id | int | 是 | 工单 ID |

**响应：**
```json
{
  "code": 200,
  "data": {
    "order_id": 1,
    "phone": "138****8000",
    "ent_name": "某某科技有限公司",
    "order_type": 1,
    "dialogues": [
      {
        "inspection_id": 1,
        "dia_id": 101,
        "content": {
          "content": "您好，请问有什么可以帮您？",
          "role": "AI",
          "msg_time": "2026-07-18T09:30:05"
        },
        "evaluation": null,
        "inspection_status": 0
      },
      {
        "inspection_id": 3,
        "dia_id": 103,
        "content": {
          "content": "营业执照办理需要准备以下材料：1. ...",
          "role": "worker",
          "msg_time": "2026-07-18T09:31:00"
        },
        "evaluation": "回答准确，态度良好",
        "inspection_status": 1
      }
    ]
  }
}
```

**错误响应：**
```json
{ "code": 404, "message": "工单不存在：order_id=999" }
```

#### `POST /api/quality-inspection/orders/{order_id}/evaluate` — 提交/更新质检评价（批量）

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| order_id | int | 是 | 工单 ID |

**请求体：**
```json
{
  "evaluations": [
    { "inspection_id": 1, "evaluation": "开场白规范，符合要求" },
    { "inspection_id": 2, "evaluation": null },
    { "inspection_id": 3, "evaluation": "回答准确，但语速偏快" }
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| evaluations | array | 是 | 评价列表，支持批量更新 |
| evaluations[].inspection_id | int | 是 | 质检记录 ID |
| evaluations[].evaluation | string/null | 是 | 评价内容，传 null 表示清空评价 |

**响应：**
```json
{
  "code": 200,
  "message": "评价保存成功",
  "data": {
    "order_id": 1,
    "evaluated_count": 2,
    "total_count": 3
  }
}
```

**错误响应：**
```json
{ "code": 400, "message": "质检记录 inspection_id=99 不属于工单 order_id=1" }
{ "code": 400, "message": "evaluations 不能为空" }
```

#### `GET /api/quality-inspection/results` — 查询质检结果（多条件筛选）

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date_from | string | 否 | 开始日期 YYYY-MM-DD |
| date_to | string | 否 | 结束日期 YYYY-MM-DD |
| order_id | int | 否 | 指定工单 ID |
| inspection_status | int | 否 | 0-待评价 1-已评价 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |

**响应：**
```json
{
  "code": 200,
  "data": {
    "total": 128,
    "page": 1,
    "page_size": 20,
    "results": [
      {
        "inspection_id": 1,
        "order_id": 1,
        "dia_id": 101,
        "content": {
          "content": "您好，请问有什么可以帮您？",
          "role": "AI",
          "msg_time": "2026-07-18T09:30:05"
        },
        "evaluation": "开场白规范，符合标准话术",
        "inspection_status": 1
      }
    ]
  }
}
```

---

### 2.9 知识库模块

#### `POST /api/knowledge-base/upload` — 上传知识库文件

支持 `.xlsx`, `.xls`, `.pdf`, `.txt`, `.docx`, `.csv`，最大 50MB。

**请求：** `multipart/form-data`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | 是 | 上传的文件 |
| description | string | 否 | 文件描述 |

**响应：**
```json
{
  "code": 200,
  "message": "上传成功",
  "data": {
    "file_id": 1,
    "file_name": "知识库-营业执照办理FAQ.xlsx",
    "file_path": "d:\\IVR\\knowledge-base\\20260718_153045_a1b2c3d4_知识库-营业执照办理FAQ.xlsx",
    "file_type": "xlsx",
    "file_size": 245760,
    "status": 1,
    "upload_time": "2026-07-18T15:30:45",
    "description": "2026年7月更新版营业执照办理常见问题"
  }
}
```

**错误响应：**
```json
{ "code": 400, "message": "不支持的文件类型：.jpg，允许的类型：.xlsx, .xls, .pdf, .txt, .docx, .csv" }
{ "code": 400, "message": "文件大小 62MB 超出限制，最大允许 50MB" }
{ "code": 400, "message": "请选择要上传的文件" }
```

#### `GET /api/knowledge-base/files` — 获取知识库文件列表

**查询参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | int | 否 | 筛选状态：0-处理中 1-已启用 2-已停用 |
| page | int | 否 | 页码，默认 1 |
| page_size | int | 否 | 每页条数，默认 20 |

**响应：**
```json
{
  "code": 200,
  "data": {
    "total": 5,
    "page": 1,
    "page_size": 20,
    "files": [
      {
        "file_id": 1,
        "file_name": "知识库-营业执照办理FAQ.xlsx",
        "file_path": "d:\\IVR\\knowledge-base\\20260718_153045_a1b2c3d4_知识库-营业执照办理FAQ.xlsx",
        "file_type": "xlsx",
        "file_size": 245760,
        "status": 1,
        "upload_time": "2026-07-18T15:30:45",
        "description": "2026年7月更新版营业执照办理常见问题"
      }
    ]
  }
}
```

#### `DELETE /api/knowledge-base/files/{file_id}` — 删除知识库文件

删除数据库记录 + 服务器上的物理文件。

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_id | int | 是 | 文件 ID |

**响应：**
```json
{ "code": 200, "message": "删除成功" }
```

**错误响应：**
```json
{ "code": 404, "message": "知识库文件不存在：file_id=99" }
```

#### `PUT /api/knowledge-base/files/{file_id}/status` — 更新文件启用/停用状态

**路径参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_id | int | 是 | 文件 ID |

**请求体：**
```json
{
  "status": 1
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | int | 是 | 1-启用 2-停用 |

**响应：**
```json
{
  "code": 200,
  "message": "状态更新成功",
  "data": {
    "file_id": 1,
    "file_name": "知识库-营业执照办理FAQ.xlsx",
    "status": 2
  }
}
```

**错误响应：**
```json
{ "code": 400, "message": "无效的状态值：3，允许的值：1-启用 2-停用" }
{ "code": 404, "message": "知识库文件不存在：file_id=99" }
```

---

## 三、数据库表结构

### 3.1 `work_order` — 主工单表

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| order_id | BigInteger (PK) | 否 | 自增主键 |
| conversation_id | String(64) | 否 | CCC 会话 ID |
| instance_id | String(64) | 否 | 热线机器人实例 ID |
| phone | String(20) | 否 | 来电号码 |
| ent_name | String(100) | 是 | 企业名称 |
| ent_address | String(500) | 是 | 经营地址 |
| ent_cerdit | String(18) | 是 | 统一社会信用代码 |
| contact_name | String(100) | 是 | 联系人姓名 |
| order_type | SmallInteger | 否 | 工单类型：0-转播 1-咨询 2-投诉 3-回访 |
| order_status | SmallInteger | 否 | 工单状态：0-主动挂断 1-处理中 2-已办结 3-待回访 4-排队中 5-振铃中 |
| agent_id | BigInteger | 是 | 受理坐席 ID |
| created_time | DateTime | 否 | 工单创建时间（IVR阶段） |
| update_time | DateTime | 是 | 最后更新时间 |
| call_start_time | DateTime | 否 | 通话开始时间 |
| call_end_time | DateTime | 是 | 通话结束时间 |
| biz_summary | Text | 是 | 业务诉求/工单摘要 |
| ai_failure_note | Text | 是 | AI未解决问题记录 |
| ai_solved | SmallInteger | 否 | AI是否解决：0-否 1-是 |

**索引：** `idx_order_phone`, `idx_order_type_status`, `idx_order_created_time`, `idx_order_agent_id`
**唯一约束：** `uk_instance_conversation (instance_id, conversation_id)`

### 3.2 `dialogue_detail` — 对话明细表

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| dia_id | BigInteger (PK) | 否 | 自增主键 |
| order_id | BigInteger (FK) | 否 | 关联工单 |
| content | Text | 否 | 单条消息内容（语音转写文本） |
| role | String(20) | 否 | 发言角色：AI / user / worker / ivr |
| msg_time | DateTime | 否 | 每条消息时间 |

**索引：** `idx_order_role_time` (order_id, role, msg_time)

### 3.3 `agent_info` — 坐席表

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| agent_id | BigInteger (PK) | 否 | 自增主键 |
| agent_name | String(50) | 否 | 坐席姓名 |
| agent_status | SmallInteger | 否 | 坐席状态：0-离线 1-忙碌 2-在线 |
| ccc_agent_id | String(100) | 是 | CCC 坐席 ID |

**索引：** `idx_agent_status`, `idx_agent_ccc_id`

### 3.4 `quality_inspection` — 质检记录表

每条对话对应一条质检记录，`content` 字段存储消息快照的 JSON。

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| inspection_id | BigInteger (PK) | 否 | 自增主键 |
| order_id | BigInteger (FK → work_order.order_id) | 否 | 关联工单 ID |
| dia_id | BigInteger (FK → dialogue_detail.dia_id) | 否 | 关联对话明细 ID |
| content | JSONB | 否 | 消息快照 JSON：`{"content": "...", "role": "AI", "msg_time": "..."}` |
| evaluation | Text | 是 | 评价内容（初始为空，质检员手动填写） |
| inspection_status | SmallInteger | 否 | 质检状态：0-待评价 1-已评价（默认 0） |

**索引：** `idx_qi_order_id`, `idx_qi_dia_id`, `idx_qi_status`
**唯一约束：** `idx_qi_order_dia (order_id, dia_id)`

**`content` 字段 JSON 结构示例：**
```json
{
  "content": "您好，请问有什么可以帮您？",
  "role": "AI",
  "msg_time": "2026-07-18T09:30:05"
}
```

**DDL 参考：**
```sql
CREATE TABLE quality_inspection (
    inspection_id   BIGSERIAL PRIMARY KEY,
    order_id        BIGINT NOT NULL REFERENCES work_order(order_id),
    dia_id          BIGINT NOT NULL REFERENCES dialogue_detail(dia_id),
    content         JSONB NOT NULL,
    evaluation      TEXT,
    inspection_status SMALLINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_qi_order_id ON quality_inspection(order_id);
CREATE INDEX idx_qi_dia_id ON quality_inspection(dia_id);
CREATE INDEX idx_qi_status ON quality_inspection(inspection_status);
CREATE UNIQUE INDEX idx_qi_order_dia ON quality_inspection(order_id, dia_id);
```

### 3.5 `knowledge_base_files` — 知识库文件表

记录上传的知识库文件元信息。

| 字段 | 类型 | 可空 | 说明 |
|------|------|------|------|
| file_id | BigInteger (PK) | 否 | 自增主键 |
| file_name | String(255) | 否 | 原始文件名 |
| file_path | String(500) | 否 | 服务器存储路径 |
| file_type | String(20) | 否 | 文件类型：xlsx / pdf / txt / docx / csv |
| file_size | BigInteger | 否 | 文件大小（字节） |
| status | SmallInteger | 否 | 状态：0-处理中 1-已启用 2-已停用（默认 1） |
| upload_time | DateTime | 否 | 上传时间 |
| description | String(500) | 是 | 文件描述/备注 |

**索引：** `idx_kbf_status`, `idx_kbf_upload_time`

**DDL 参考：**
```sql
CREATE TABLE knowledge_base_files (
    file_id       BIGSERIAL PRIMARY KEY,
    file_name     VARCHAR(255) NOT NULL,
    file_path     VARCHAR(500) NOT NULL,
    file_type     VARCHAR(20) NOT NULL,
    file_size     BIGINT NOT NULL,
    status        SMALLINT NOT NULL DEFAULT 1,
    upload_time   TIMESTAMP NOT NULL DEFAULT NOW(),
    description   VARCHAR(500)
);

CREATE INDEX idx_kbf_status ON knowledge_base_files(status);
CREATE INDEX idx_kbf_upload_time ON knowledge_base_files(upload_time);
```

---

## 四、Redis 键约定

| 键模式 | 类型 | TTL | 说明 |
|--------|------|-----|------|
| `robot:slot:{slot_id}` | String (JSON) | 永久 | 槽位状态：`{status, order_id, session_id, started_at}` |
| `robot:queue` | List | 永久 | 排队队列：`[{order_id, phone, joined_at}, ...]` |
| `history:{order_id}` | List (JSON) | 永久 | 历史对话：`[{role, content, time}, ...]`，滑动窗口保留最近 40 条 |
| `call:pending:{conv_id}` | String (JSON) | 300s | 来电暂存：`{phone, instance_id}`，等待 IVR 按键分流 |
| `ccc:event:{event_id}` | String | 3600s | 事件去重：幂等标记，防止重复处理 |
| `agent:{agent_id}:status` | String | 永久 | 坐席状态缓存：idle / busy / offline |

### 槽位状态 JSON 示例

```json
// busy
{ "status": "busy", "order_id": 1, "session_id": "uuid-xxx", "started_at": 1720000000.0 }

// idle
{ "status": "idle", "order_id": null, "session_id": null, "started_at": null }
```

### 历史对话 JSON 示例

```json
[
  { "role": "user", "content": "我想咨询营业执照", "time": "10:00:05" },
  { "role": "bot",  "content": "您好，请问...", "time": "10:00:06" }
]
```

---

## 五、helpers.py 辅助函数

DB 同事可通过 `from tests.helpers import *` 使用以下函数。
兼容 `TestClient`（pytest 内联测试，`base_url=""`）和 `httpx.Client`（远程调用，`base_url="http://localhost:8000"`）。

| 函数 | 说明 |
|------|------|
| `create_test_order(client, phone, conv_id, order_type, instance_id, base_url)` | 创建测试工单 |
| `simulate_ivr_event(client, event_type, conversation_id, key, caller, instance_id, base_url)` | 模拟 CCC 事件 |
| `simulate_call_started(client, conversation_id, phone, instance_id, base_url)` | 模拟来电接入 |
| `simulate_ivr_key(client, conversation_id, key, base_url)` | 模拟 IVR 按键 |
| `simulate_hangup(client, conversation_id, hangup_dir, base_url)` | 模拟挂断 |
| `assign_robot_slot(client, order_id, phone, base_url)` | 分配智能坐席槽位 |
| `release_robot_slot(client, slot_id, base_url)` | 释放槽位 |
| `simulate_dialogue(client, order_id, utterance, base_url)` | 模拟一轮机器人对话 |
| `get_order(client, order_id, base_url)` | 获取工单详情 |
| `get_orders_by_phone(client, phone, base_url)` | 根据电话查历史工单 |
| `get_slot_status(client, base_url)` | 获取所有槽位状态 |
| `get_agents(client, base_url)` | 获取所有坐席（agent_info 表） |
| `update_agent_status(client, agent_id, agent_status, ...)` | 更新坐席状态 |
| `dispatch_order(client, order_id, receiver, base_url)` | 工单完结流转推送 |

### 使用示例（远程调用正在运行的服务）

```python
import httpx
from tests.helpers import simulate_call_started, simulate_ivr_key, simulate_dialogue

client = httpx.Client(base_url="http://localhost:8000")

# 模拟来电
simulate_call_started(client, "conv-001", "13800138000", base_url="http://localhost:8000")
# 模拟按键1（企业咨询）
simulate_ivr_key(client, "conv-001", "1", base_url="http://localhost:8000")
# 模拟对话
simulate_dialogue(client, order_id=1, utterance="我想咨询营业执照", base_url="http://localhost:8000")
```

### 使用示例（pytest 内联测试，使用 TestClient）

```python
from tests.helpers import simulate_call_started, simulate_ivr_key

def test_my_scenario(app_client):
    # base_url 默认为 ""，适配 TestClient
    simulate_call_started(app_client, "conv-001", "13800138000")
    simulate_ivr_key(app_client, "conv-001", "1")
```

---

## 六、DB 同事脚本说明

### `database/seed_data.py` — 初始化测试数据

```bash
python -m database.seed_data           # 清理旧数据 + 创建测试坐席 + 初始化槽位
python -m database.seed_data --check   # 仅查看当前状态（不修改）
```

**功能：**
- 清理 PostgreSQL（work_order + dialogue_detail + agent_info）
- 清理 Redis（槽位、队列、历史对话、来电缓存、事件去重、坐席状态）
- 创建 2 个测试坐席（测试坐席A/B，状态=在线空闲）
- 初始化所有槽位为 idle

### `database/verify_data.py` — 验证数据正确性

```bash
python -m database.verify_data
# 退出码: 0=全部通过, 1=存在失败项
```

**验证项：**
- 工单表：必填字段非空、枚举值范围、时间逻辑、办结工单摘要
- 对话明细表：role 有效范围、content 非空、关联工单存在
- 坐席表：agent_status 范围、agent_name 非空
- 槽位状态：busy 槽位的 order_id 在工单表中存在、已办结工单不应占用槽位
- Redis 一致性：历史对话与数据库对话明细的对应关系

### `database/export_test_data.py` — 导出测试数据

```bash
python -m database.export_test_data                       # 导出到本地 test_export.json
python -m database.export_test_data --upload              # 导出并上传 OSS
python -m database.export_test_data --output result.json  # 指定输出文件名
```

**导出内容：**
- 所有工单（含全部字段）
- 所有对话明细
- 所有坐席
- Redis 状态（槽位、排队队列、历史对话、来电缓存）

**OSS 上传：** OSS 配置完整时上传到 OSS，未配置时降级保存到本地 `test-reports/local/` 目录。

---

## 七、测试范围说明

| 组件 | 测试时 | 说明 |
|------|--------|------|
| 阿里云 CCC | **真实** | 真实调用 BlindTransfer/SignInGroup 等 API |
| Beebot 对话 | **真实** | 真实调用 Chat API（begin_session/dialogue） |
| RocketMQ | 不启动 | 事件通过 `/api/ccc/callback` 直接 POST（绕过消息队列） |
| PostgreSQL | **真实** | 真实数据库读写 |
| Redis | **真实** | 真实 Redis 读写 |
| LLM Skill | **真实** | 真实调用 DashScope API |
| OSS | 可选 | 配置完整时真实上传，否则降级本地 |

### 假数据使用范围

仅 CCC **事件入口**使用假数据（绕过 RocketMQ 事件通道）：

- `CallStarted` — 假的来电号码、会话ID
- `IvrKeyPressed` — 假的按键（1/2/0）
- `CallHangup` — 假的挂断方向
- `AsrSentenceResult` — 假的语音转写文本

这些事件通过 `/api/ccc/callback` 接口直接 POST，模拟 RocketMQ 推送的事件。
事件触发后的所有业务逻辑（包括 CCC API 调用、Beebot 对话）都是真实的。
