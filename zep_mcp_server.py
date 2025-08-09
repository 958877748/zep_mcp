import os
import json
import asyncio
import uuid as uuidlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# 尽量兼容 fastmcp 与 mcp.server 的导入方式
try:
    from mcp.server.fastmcp import FastMCP as MCPServer
except Exception:  # pragma: no cover - 作为兼容回退
    from mcp.server import Server as MCPServer  # type: ignore


# Zep Python SDK（collections/search 等）
try:
    # 参考本仓库文档 Zep_SDK_Quickstart.md
    from zep_python import ZepClient  # type: ignore
except Exception:  # pragma: no cover
    ZepClient = None  # 占位，运行时若为 None 会报错引导安装依赖

# Zep Cloud SDK（thread.add_messages）
try:
    from zep_cloud import Zep as CloudZep, Message as CloudMessage  # type: ignore
except Exception:  # pragma: no cover
    CloudZep = None
    CloudMessage = None


# ==== 配置 ====
ZEP_API_KEY = os.environ.get("ZEP_API_KEY")
ZEP_API_URL = os.environ.get("ZEP_API_URL")

# 将 Graphiti 的概念映射为 Zep 的集合
COLLECTION_NODES = os.environ.get("ZEP_COLLECTION_NODES", "nodes")
COLLECTION_EDGES = os.environ.get("ZEP_COLLECTION_EDGES", "edges")
COLLECTION_EPISODES = os.environ.get("ZEP_COLLECTION_EPISODES", "episodes")

# get_episodes 中的默认 group_id（若未传参）
DEFAULT_GROUP_ID = os.environ.get("ZEP_DEFAULT_GROUP_ID")


# ==== Zep 客户端初始化 ====
if ZepClient is None:
    raise RuntimeError(
        "zep-python 未安装。请先安装依赖：pip install zep-python mcp"
    )

zep_client = ZepClient(api_key=ZEP_API_KEY, base_url=ZEP_API_URL)

# 可选：Zep Cloud 客户端，仅用于 thread.add_messages
zep_cloud_client = None
if CloudZep is not None:
    try:
        # 官方示例仅需 api_key；base_url 让 SDK 自行默认
        zep_cloud_client = CloudZep(api_key=ZEP_API_KEY)
    except Exception:
        zep_cloud_client = None


# ==== MCP 服务器 ====
server = MCPServer("zep-mcp")


# ==== 工具层通用帮助函数 ====
async def ensure_collection(name: str) -> None:
    """确保集合存在；若不存在则创建。"""
    try:
        # 尝试读取集合，存在则返回
        await zep_client.collections.get(name)  # type: ignore[attr-defined]
        return
    except Exception:
        # 不存在则创建（忽略并发冲突）
        try:
            await zep_client.collections.create({"name": name})  # type: ignore[attr-defined]
        except Exception:
            # 可能在并发下已经被创建
            pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_uuid() -> str:
    return str(uuidlib.uuid4())


async def zep_documents_add(collection: str, docs: List[Dict[str, Any]]) -> Any:
    await ensure_collection(collection)
    return await zep_client.documents.add(collection, docs)  # type: ignore[attr-defined]


async def zep_documents_delete(collection: str, ids: List[str]) -> Any:
    await ensure_collection(collection)
    # 部分 SDK 形态是批量删除
    return await zep_client.documents.delete(collection, ids)  # type: ignore[attr-defined]


async def zep_document_get(collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
    await ensure_collection(collection)
    try:
        return await zep_client.documents.get(collection, doc_id)  # type: ignore[attr-defined]
    except Exception:
        return None


async def semantic_search(
    collection: str,
    query: str,
    top_k: int,
    where: Optional[Dict[str, Any]] = None,
    include_metadata: bool = True,
) -> List[Dict[str, Any]]:
    await ensure_collection(collection)
    payload = {
        "query": query or "",
        "topK": top_k,
        "includeMetadata": include_metadata,
    }
    if where:
        # 兼容不同 SDK 的筛选字段命名
        payload["where"] = where
        payload["filter"] = where
    try:
        result = await zep_client.search.semantic(collection, payload)  # type: ignore[attr-defined]
        # 标准化：将结果列表中的 item 统一转为 {id, content, metadata, score}
        normalized: List[Dict[str, Any]] = []
        if isinstance(result, list):
            for item in result:
                normalized.append(
                    {
                        "id": item.get("id") if isinstance(item, dict) else None,
                        "content": item.get("content") if isinstance(item, dict) else None,
                        "metadata": item.get("metadata") if isinstance(item, dict) else None,
                        "score": item.get("score") if isinstance(item, dict) else None,
                        "raw": item,
                    }
                )
        return normalized
    except Exception as e:
        # 回退：若搜索不可用，直接返回空
        return []


# 线程消息追加：兼容不同版本 SDK 的方法命名
async def add_messages_to_thread(
    thread_id: str, messages: List[Dict[str, Any]]
) -> Any:
    """将消息追加到线程/会话。
    首选 zep_cloud 的 client.thread.add_messages；
    若不可用，则尝试 zep_python 的 thread(s).add_messages；
    最后回退到 messages.add(session_id, messages)。
    """
    # 优先使用 zep_cloud（官方示例）
    if zep_cloud_client is not None and CloudMessage is not None:
        def _call():
            cloud_messages = [
                CloudMessage(content=m.get("content", ""), role=m.get("role", "user"))
                for m in messages
            ]
            return zep_cloud_client.thread.add_messages(
                thread_id=thread_id, messages=cloud_messages
            )

        try:
            # 同步 API 放到线程池避免阻塞事件循环
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _call)
        except RuntimeError:
            # 在无事件循环环境下（极少数情况）直接调用
            return _call()

    # 次选：zep_python 的 thread/threads API
    thread_api = getattr(zep_client, "thread", None)
    if thread_api is not None and hasattr(thread_api, "add_messages"):
        return await thread_api.add_messages(thread_id, messages)  # type: ignore[attr-defined]

    threads_api = getattr(zep_client, "threads", None)
    if threads_api is not None and hasattr(threads_api, "add_messages"):
        return await threads_api.add_messages(thread_id, messages)  # type: ignore[attr-defined]

    # 回退：旧接口 messages.add
    messages_api = getattr(zep_client, "messages", None)
    if messages_api is not None and hasattr(messages_api, "add"):
        return await messages_api.add(thread_id, messages)  # type: ignore[attr-defined]

    raise RuntimeError(
        "未找到可用的 add_messages 方法（已尝试 zep_cloud.thread、zep_python.thread(s)、messages.add）。"
    )


# ==== 8 个工具 ====

@server.tool()
async def add_memory(
    name: str,
    episode_body: str,
    group_id: Optional[str] = None,
    source: str = "text",
    source_description: str = "",
    uuid: Optional[str] = None,
) -> Dict[str, Any]:
    """
    使用 Zep 的 Thread add-messages API 追加一条（或多条）消息。
    - 使用 group_id 作为 thread_id；若未提供，则尝试 DEFAULT_GROUP_ID。
    - 支持 text/json/message 三种 source；统一通过消息 metadata 附带来源信息。
    """
    thread_id = group_id or DEFAULT_GROUP_ID or "default"
    message_uuid = uuid or generate_uuid()

    # 生成公共 metadata
    common_metadata: Dict[str, Any] = {
        "name": name,
        "source": source,
        "source_description": source_description,
        "group_id": thread_id,
        "created_at": now_iso(),
        "type": "episode",
        # 将我们生成/传入的 uuid 记录在 metadata，便于后续检索
        "graphiti_uuid": message_uuid,
    }

    messages: List[Dict[str, Any]] = []

    if source == "message":
        # 尝试把 episode_body 解析为单条或多条消息
        parsed: Any = None
        try:
            parsed = json.loads(episode_body)
        except json.JSONDecodeError:
            parsed = None

        def normalize_content(value: Any) -> str:
            return (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False)
            )

        if isinstance(parsed, list):
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                role = item.get("role") or "user"
                content = normalize_content(item.get("content"))
                messages.append(
                    {
                        "role": role,
                        "content": content,
                        "metadata": {**common_metadata},
                    }
                )
        elif isinstance(parsed, dict) and (
            "role" in parsed or "content" in parsed
        ):
            role = parsed.get("role") or "user"
            content = normalize_content(parsed.get("content"))
            messages.append(
                {"role": role, "content": content, "metadata": {**common_metadata}}
            )
        else:
            # 非 JSON 或不符合结构，按单条用户消息落盘
            messages.append(
                {
                    "role": "user",
                    "content": episode_body,
                    "metadata": {**common_metadata},
                }
            )
    else:
        # text 或 json（json 作为字符串内容发送）
        content_str: str
        if source == "json":
            try:
                parsed = json.loads(episode_body)
                content_str = json.dumps(parsed, ensure_ascii=False)
            except json.JSONDecodeError:
                content_str = episode_body
        else:
            content_str = episode_body

        messages.append(
            {"role": "user", "content": content_str, "metadata": {**common_metadata}}
        )

    # 调用线程消息追加 API（根据 SDK 版本自动适配）
    await add_messages_to_thread(thread_id, messages)

    return {
        "message": f"message(s) enqueued to thread={thread_id}",
        "thread_id": thread_id,
        "uuid": message_uuid,
        "count": len(messages),
    }


@server.tool()
async def search_memory_nodes(
    query: str,
    group_ids: Optional[List[str]] = None,
    max_nodes: int = 10,
    center_node_uuid: Optional[str] = None,
    entity: str = "",
) -> Dict[str, Any]:
    """
    近似 Graphiti 的节点检索：在 `nodes` 集合上做语义搜索，并基于 metadata 做过滤。
    - entity 用作 labels/type 过滤。
    - center_node_uuid 仅记录在响应中，不做图距离排序（Zep 无图结构）。
    """
    where: Dict[str, Any] = {}
    if group_ids:
        where["group_id"] = {"$in": group_ids}
    if entity:
        # 假设节点文档的 metadata.labels 或 metadata.type 持有实体类型
        where["$or"] = [
            {"labels": {"$contains": entity}},
            {"type": entity},
        ]

    results = await semantic_search(
        COLLECTION_NODES, query=query, top_k=max_nodes, where=where
    )

    nodes: List[Dict[str, Any]] = []
    for r in results:
        metadata = r.get("metadata") or {}
        nodes.append(
            {
                "uuid": r.get("id"),
                "name": metadata.get("name") or (r.get("content") or "")[:64],
                "summary": metadata.get("summary") or r.get("content"),
                "labels": metadata.get("labels") or metadata.get("type"),
                "group_id": metadata.get("group_id"),
                "created_at": metadata.get("created_at"),
                "attributes": metadata.get("attributes") or {},
                "score": r.get("score"),
            }
        )

    return {
        "message": f"found {len(nodes)} node(s)",
        "center_node_uuid": center_node_uuid,
        "nodes": nodes,
    }


@server.tool()
async def search_memory_facts(
    query: str,
    group_ids: Optional[List[str]] = None,
    max_facts: int = 10,
    center_node_uuid: Optional[str] = None,
) -> Dict[str, Any]:
    """
    近似 Graphiti 的事实（边）检索：在 `edges` 集合上做语义搜索，并基于 metadata 过滤。
    """
    if max_facts <= 0:
        return {"error": "max_facts must be > 0"}

    where: Dict[str, Any] = {}
    if group_ids:
        where["group_id"] = {"$in": group_ids}

    results = await semantic_search(
        COLLECTION_EDGES, query=query, top_k=max_facts, where=where
    )

    facts: List[Dict[str, Any]] = []
    for r in results:
        metadata = r.get("metadata") or {}
        facts.append(
            {
                "uuid": r.get("id"),
                "from_uuid": metadata.get("from_uuid"),
                "to_uuid": metadata.get("to_uuid"),
                "relation_type": metadata.get("relation_type") or metadata.get("type"),
                "group_id": metadata.get("group_id"),
                "created_at": metadata.get("created_at"),
                "attributes": metadata.get("attributes") or {},
                "score": r.get("score"),
            }
        )

    return {"message": f"found {len(facts)} fact(s)", "facts": facts}


@server.tool()
async def delete_entity_edge(uuid: str) -> Dict[str, Any]:
    """删除 `edges` 集合中的一条边文档。"""
    await ensure_collection(COLLECTION_EDGES)
    await zep_documents_delete(COLLECTION_EDGES, [uuid])
    return {"message": f"edge deleted: {uuid}"}


@server.tool()
async def delete_episode(uuid: str) -> Dict[str, Any]:
    """删除 `episodes` 集合中的一条文档。"""
    await ensure_collection(COLLECTION_EPISODES)
    await zep_documents_delete(COLLECTION_EPISODES, [uuid])
    return {"message": f"episode deleted: {uuid}"}


@server.tool()
async def get_entity_edge(uuid: str) -> Dict[str, Any]:
    """读取 `edges` 集合中的一条边文档。"""
    edge = await zep_document_get(COLLECTION_EDGES, uuid)
    if edge is None:
        return {"error": f"edge not found: {uuid}"}

    return {
        "uuid": edge.get("id"),
        "content": edge.get("content"),
        "metadata": edge.get("metadata"),
    }


@server.tool()
async def get_episodes(
    group_id: Optional[str] = None,
    last_n: int = 10,
) -> Dict[str, Any]:
    """
    近似 Graphiti 的 get_episodes：按 group_id 过滤 `episodes` 集合并返回最近 N 条。
    注意：若 SDK 暂不支持基于时间排序，这里按语义检索回传顺序/本地时间字段降序截断。
    """
    effective_group_id = group_id or DEFAULT_GROUP_ID or "default"

    # 这里用一个空查询，主要依赖 where 过滤
    where = {"group_id": effective_group_id}
    results = await semantic_search(
        COLLECTION_EPISODES, query="", top_k=max(50, last_n), where=where
    )

    # 本地基于 created_at 进行降序排序
    def parse_ts(item: Dict[str, Any]) -> float:
        md = item.get("metadata") or {}
        ts = md.get("created_at")
        try:
            return datetime.fromisoformat(ts).timestamp() if ts else 0.0
        except Exception:
            return 0.0

    results_sorted = sorted(results, key=parse_ts, reverse=True)
    selected = results_sorted[: last_n or 10]

    episodes: List[Dict[str, Any]] = []
    for r in selected:
        episodes.append(
            {
                "uuid": r.get("id"),
                "content": r.get("content"),
                "metadata": r.get("metadata"),
            }
        )

    return {"message": f"found {len(episodes)} episode(s)", "episodes": episodes}


@server.tool()
async def clear_graph() -> Dict[str, Any]:
    """删除 nodes/edges/episodes 三个集合中的全部文档（或直接删除集合）。"""
    # 简单做法：尝试删除集合（若 SDK 不支持删除集合，则退化为批量删除文档）
    async def try_delete_collection(name: str) -> None:
        try:
            await zep_client.collections.delete(name)  # type: ignore[attr-defined]
        except Exception:
            # 回退：无法删集合时，不做进一步处理（也可在此实现 list+batch delete）
            pass

    await try_delete_collection(COLLECTION_NODES)
    await try_delete_collection(COLLECTION_EDGES)
    await try_delete_collection(COLLECTION_EPISODES)

    # 重建空集合，便于后续写入
    await ensure_collection(COLLECTION_NODES)
    await ensure_collection(COLLECTION_EDGES)
    await ensure_collection(COLLECTION_EPISODES)

    return {"message": "graph cleared (collections reset)"}


# 可选：健康检查资源（与 Graphiti 的资源类似，但不计入 8 个工具）
try:
    @server.resource("http://zep/status")
    async def get_status() -> Dict[str, Any]:  # type: ignore[misc]
        return {
            "status": "ok",
            "time": now_iso(),
            "collections": [
                COLLECTION_NODES,
                COLLECTION_EDGES,
                COLLECTION_EPISODES,
            ],
        }
except Exception:
    # 某些 MCP 运行时可能没有 resource 装饰器
    pass


if __name__ == "__main__":
    # FastMCP 提供 .run()；若使用 mcp.server.Server，运行方式可能不同
    try:
        server.run()
    except AttributeError:
        # 兼容旧版：提供一个简单的 asyncio 阻塞，防止意外退出
        asyncio.get_event_loop().run_forever()
