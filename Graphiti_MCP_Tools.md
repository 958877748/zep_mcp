## Graphiti MCP Server 工具清单（来自 getzep/graphiti mcp_server/graphiti_mcp_server.py）

来源：`https://github.com/getzep/graphiti` 仓库 `mcp_server/graphiti_mcp_server.py`

文档包含 8 个 MCP tool：名称、描述、参数与执行逻辑（基于源码解析，概述返回值）。

---

### 1) add_memory
- **名称**: `add_memory`
- **描述**: 向知识图谱新增一条“记忆”事件（Episode）。该调用会“立即返回”，真实的写入在后台队列中按 `group_id` 顺序依次处理，避免并发竞态。
- **参数**:
  - `name: str`：事件名称。
  - `episode_body: str`：正文内容；当 `source='json'` 时必须是正确转义的 JSON 字符串。
  - `group_id: str | None = None`：图的命名空间；未提供时回退到全局配置的 `group_id`。
  - `source: str = 'text'`：来源类型，`text | json | message`。
  - `source_description: str = ''`：来源描述。
  - `uuid: str | None = None`：可选自定义 UUID。
- **执行逻辑**:
  - 校验全局 `graphiti_client` 已初始化。
  - 将 `source` 映射为 `EpisodeType`（`text`/`message`/`json`）。
  - 采用 `group_id` 或全局配置的默认值；为每个 `group_id` 维持一个 `asyncio.Queue`。
  - 将真正的写入操作封装为异步函数入队：内部调用 `Graphiti.add_episode()`，并：
    - 若启用自定义实体抽取（`use_custom_entities=true`），传入内置的 `ENTITY_TYPES`（`Requirement`/`Preference`/`Procedure`）。
    - 使用 `datetime.now(timezone.utc)` 作为参考时间。
  - 如对应 `group_id` 的队列 worker 未启动，则启动一个顺序处理任务。
  - 立即返回成功消息，包含当前队列位置；失败则返回错误。
- **返回**: `SuccessResponse { message }` 或 `ErrorResponse { error }`。

---

### 2) search_memory_nodes
- **名称**: `search_memory_nodes`
- **描述**: 在图记忆中检索“节点摘要”（包含与其它节点的关系总结）。可按实体类型过滤并支持以中心节点为参考的检索。
- **参数**:
  - `query: str`：查询语句。
  - `group_ids: list[str] | None = None`：可选的 `group_id` 列表；为空时回退到全局配置的 `group_id`（如有）。
  - `max_nodes: int = 10`：最大返回节点数。
  - `center_node_uuid: str | None = None`：可选中心节点 UUID，用于围绕该节点的相关性检索。
  - `entity: str = ''`：单一实体类型过滤（允许：`Preference`、`Procedure`；留空则不限定）。
- **执行逻辑**:
  - 校验 `graphiti_client`。
  - 组装 `effective_group_ids`。
  - 选择检索配置：
    - 有 `center_node_uuid`：复制 `NODE_HYBRID_SEARCH_NODE_DISTANCE`；
    - 否则：复制 `NODE_HYBRID_SEARCH_RRF`；并设置 `limit = max_nodes`。
  - 如提供 `entity`，将其设为 `SearchFilters.node_labels`。
  - 调用私有 `_search(query, config, group_ids, center_node_uuid, search_filter)`。
  - 将结果节点格式化为 `{ uuid, name, summary, labels, group_id, created_at(ISO), attributes }` 列表。
- **返回**: `NodeSearchResponse { message, nodes[] }` 或 `ErrorResponse { error }`。

---

### 3) search_memory_facts
- **名称**: `search_memory_facts`
- **描述**: 在图记忆中检索“事实”（实体间的边/关系）。
- **参数**:
  - `query: str`：查询语句。
  - `group_ids: list[str] | None = None`：可选的 `group_id` 列表；为空时回退到全局配置的 `group_id`（如有）。
  - `max_facts: int = 10`：最大返回事实数；必须为正数。
  - `center_node_uuid: str | None = None`：可选中心节点 UUID。
- **执行逻辑**:
  - 校验 `graphiti_client`；校验 `max_facts > 0`。
  - 组装 `effective_group_ids`。
  - 调用 `Graphiti.search(group_ids, query, num_results=max_facts, center_node_uuid)` 获取相关 `EntityEdge`。
  - 通过 `format_fact_result()` 序列化每条边（排除嵌入向量）。
- **返回**: `FactSearchResponse { message, facts[] }` 或 `ErrorResponse { error }`。

---

### 4) delete_entity_edge
- **名称**: `delete_entity_edge`
- **描述**: 删除一条实体边（事实）。
- **参数**:
  - `uuid: str`：实体边 UUID。
- **执行逻辑**:
  - 校验 `graphiti_client`。
  - `EntityEdge.get_by_uuid(client.driver, uuid)` 拉取对象，随后 `edge.delete(client.driver)` 删除。
- **返回**: `SuccessResponse { message }` 或 `ErrorResponse { error }`。

---

### 5) delete_episode
- **名称**: `delete_episode`
- **描述**: 删除一条事件（Episode）。
- **参数**:
  - `uuid: str`：事件 UUID。
- **执行逻辑**:
  - 校验 `graphiti_client`。
  - `EpisodicNode.get_by_uuid(client.driver, uuid)` 拉取对象，随后 `episode.delete(client.driver)` 删除。
- **返回**: `SuccessResponse { message }` 或 `ErrorResponse { error }`。

---

### 6) get_entity_edge
- **名称**: `get_entity_edge`
- **描述**: 通过 UUID 获取一条实体边（事实）的详情。
- **参数**:
  - `uuid: str`：实体边 UUID。
- **执行逻辑**:
  - 校验 `graphiti_client`。
  - `EntityEdge.get_by_uuid(client.driver, uuid)` 获取边；通过 `format_fact_result()` 转为字典（移除嵌入）。
- **返回**: `dict[str, Any]`（事实详情）或 `ErrorResponse { error }`。

---

### 7) get_episodes
- **名称**: `get_episodes`
- **描述**: 获取指定 `group_id` 下最近的若干事件。
- **参数**:
  - `group_id: str | None = None`：分组 ID；为空时回退到全局配置的 `group_id`。
  - `last_n: int = 10`：返回最近的数量。
- **执行逻辑**:
  - 校验 `graphiti_client`。
  - 采用 `effective_group_id`（确保是 `str`）。
  - 调用 `Graphiti.retrieve_episodes(group_ids=[effective_group_id], last_n, reference_time=now)`。
  - 对每个 `EpisodicNode` 执行 `model_dump(mode='json')`，以便正确序列化时间等字段。
  - 若无结果，返回 `{ message, episodes: [] }` 的结构化消息。
- **返回**: `list[dict[str, Any]]` 或 `EpisodeSearchResponse { message, episodes[] }` 或 `ErrorResponse { error }`。

---

### 8) clear_graph
- **名称**: `clear_graph`
- **描述**: 清空图数据并重建索引与约束。
- **参数**: 无
- **执行逻辑**:
  - 校验 `graphiti_client`。
  - 调用 `clear_data(client.driver)` 清空所有数据；随后 `client.build_indices_and_constraints()` 重建索引。
- **返回**: `SuccessResponse { message }` 或 `ErrorResponse { error }`。

---

### 备注
- 该文件还暴露了一个 MCP 资源 `@mcp.resource('http://graphiti/status') → get_status()`，用于健康检查（不计入上述 8 个 tool）。
- 多处 API 调用依赖全局初始化的 `Graphiti` 客户端（需正确配置 Neo4j、LLM/Embedding 等）。
- `add_memory` 采用按 `group_id` 的顺序队列保证同组内写入顺序与一致性；并发上限由 `SEMAPHORE_LIMIT` 限制在 Graphiti 内部协程层面。
