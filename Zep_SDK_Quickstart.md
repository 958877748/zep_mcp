# Zep SDK 使用指南（Python 与 JavaScript）

> 适用于在应用中集成 Zep 的会话记忆与向量检索功能。示例涵盖安装、客户端初始化、常见读写与检索流程。具体 API 形态可能随版本演进，请以官方文档为准（见文末参考）。

## 前置条件
- 已注册并获取 Zep API Key
- 可用的 Zep 服务地址：云服务或自建（例如 `http://localhost:8000`）
- Node.js 18+ 或 Python 3.9+

## 安装
```bash
# JavaScript / TypeScript
npm i @getzep/zep-js
# 或
pnpm add @getzep/zep-js
# 或
yarn add @getzep/zep-js
```

```bash
# Python
pip install zep-python
```

## 环境变量
建议使用如下环境变量：

```bash
# .env 示例
ZEP_API_KEY=your_api_key
ZEP_API_URL=https://your-zep-endpoint
```

## 初始化客户端

### JavaScript / TypeScript
```ts
import { ZepClient } from "@getzep/zep-js";

const client = new ZepClient({
  apiKey: process.env.ZEP_API_KEY,
  baseUrl: process.env.ZEP_API_URL, // 若省略，使用 SDK 默认值
});
```

### Python
```python
import os
from zep_python import ZepClient

client = ZepClient(
    api_key=os.environ.get("ZEP_API_KEY"),
    base_url=os.environ.get("ZEP_API_URL"),  # 若省略，使用 SDK 默认值
)
```

## 常见用法

> 下述示例展示典型流程与参数形态，具体方法名/参数请参考对应版本 SDK 文档。

### 1) 会话记忆（追加消息与读取）

- 追加/保存一轮对话到某个 `session_id`
- 读取该会话的历史与摘要/长期记忆，以便向 LLM 提供上下文

JavaScript：
```ts
const sessionId = "user-123";

await client.messages.add(sessionId, [
  { role: "user", content: "嗨，我叫小王" },
  { role: "assistant", content: "你好，小王！" },
]);

const history = await client.messages.list(sessionId, { limit: 20 });
// 可选：读取已提取的摘要/长期记忆（如有）
const memory = await client.memory.get(sessionId);
```

Python：
```python
session_id = "user-123"

await client.messages.add(
    session_id,
    [
        {"role": "user", "content": "嗨，我叫小王"},
        {"role": "assistant", "content": "你好，小王！"},
    ],
)

history = await client.messages.list(session_id, {"limit": 20})
# 可选：读取摘要/长期记忆（如有）
memory = await client.memory.get(session_id)
```

常见可选项：
- `limit`/`after`/`before`：分页读取消息
- `include`：控制是否包含嵌入、元数据等

### 2) 文档集合与语义搜索

- 创建集合（指定向量维度、嵌入模型等）
- 插入文档（含文本与元数据）
- 基于向量检索进行相似搜索

JavaScript：
```ts
// 创建集合
await client.collections.create({
  name: "products",
  description: "商品知识库",
  // 视部署与模型配置而定，例如：embeddingDimensions、embeddingModel、isAutoEmbed 等
});

// 插入文档
await client.documents.add("products", [
  {
    id: "sku-001",
    content: "这是一款轻薄笔记本，适合出差与办公。",
    metadata: { brand: "Acme", price: 5999, tags: ["laptop", "office"] },
  },
]);

// 相似搜索
const results = await client.search.semantic("products", {
  query: "便携办公的笔记本电脑",
  topK: 5,
  includeMetadata: true,
});
```

Python：
```python
# 创建集合
await client.collections.create({
    "name": "products",
    "description": "商品知识库",
})

# 插入文档
await client.documents.add("products", [
    {
        "id": "sku-001",
        "content": "这是一款轻薄笔记本，适合出差与办公。",
        "metadata": {"brand": "Acme", "price": 5999, "tags": ["laptop", "office"]},
    }
])

# 相似搜索
results = await client.search.semantic(
    "products",
    {
        "query": "便携办公的笔记本电脑",
        "topK": 5,
        "includeMetadata": True,
    },
)
```

常见可选项：
- `topK`：返回条数
- `scoreThreshold`：相似度阈值过滤
- `where`/`filter`：基于 `metadata` 的结构化过滤（如 brand=Acme, price<6000）
- `includeVectors`/`includeMetadata`：控制返回内容

### 3) 清理与维护

```ts
// JS：删除会话与集合
await client.sessions.delete("user-123");
await client.collections.delete("products");
```

```python
# Python：删除会话与集合
await client.sessions.delete("user-123")
await client.collections.delete("products")
```

## 超时与错误处理
- 在 Node/Python 客户端初始化或调用处设置 `timeout`、`retries`（若 SDK 提供）
- 捕获网络错误与配额错误，必要时退避重试
- 对写操作（追加消息、插入文档）做好幂等设计（如自定义 `id`）

## 最佳实践
- 将会话级上下文（姓名、偏好）放入记忆，长对话中定期读取摘要用于提示词拼接
- 文档集合按主题拆分，元数据规范化，便于检索时进行结构化过滤
- 在服务端持有 API Key，不要在前端直接暴露

## 参考
- 官方文档（概念与 API 说明）：`https://docs.getzep.com`（或 `https://zep.dev`）
- JS SDK 源码与示例：`https://github.com/getzep/zep-js`
- Python SDK 源码与示例：`https://github.com/getzep/zep-python`

> 如果你提供具体的 SDK 版本或目标功能，我可以据此补充更精确的代码示例（含方法与参数）。
