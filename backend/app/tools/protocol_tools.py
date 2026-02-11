from langchain_core.tools import BaseTool
from typing import Dict, Any, List, Optional
import os
import asyncio
import threading
from pydantic import PrivateAttr
from .base import ToolParameter

# 添加对嵌套异步的支持
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass  # 如果没有安装nest_asyncio，继续运行

# MCP服务器环境变量映射表
# 用于自动检测常见MCP服务器需要的环境变量
MCP_SERVER_ENV_MAP = {
    "server-github": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
    "server-slack": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
    "server-google-drive": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN"],
    "server-postgres": ["POSTGRES_CONNECTION_STRING"],
    "server-sqlite": [],  # 不需要环境变量
    "server-filesystem": [],  # 不需要环境变量
}


def _create_builtin_server():
    """创建内置演示服务器"""
    try:
        from fastmcp import FastMCP

        server = FastMCP("TripPlannerAgent-BuiltinServer")

        @server.tool()
        def add(a: float, b: float) -> float:
            """加法计算器"""
            return a + b

        @server.tool()
        def subtract(a: float, b: float) -> float:
            """减法计算器"""
            return a - b

        @server.tool()
        def multiply(a: float, b: float) -> float:
            """乘法计算器"""
            return a * b

        @server.tool()
        def divide(a: float, b: float) -> float:
            """除法计算器"""
            if b == 0:
                raise ValueError("除数不能为零")
            return a / b

        @server.tool()
        def greet(name: str = "World") -> str:
            """友好问候"""
            return f"Hello, {name}! 欢迎使用  MCP 工具！"

        @server.tool()
        def get_system_info() -> dict:
            """获取系统信息"""
            import platform
            import sys
            return {
                "platform": platform.system(),
                "python_version": sys.version,
                "server_name": "-BuiltinServer",
                "tools_count": 6
            }

        return server

    except ImportError:
        raise ImportError(
            "创建内置 MCP 服务器需要 fastmcp 库。请安装: pip install fastmcp"
        )


def _prepare_env(env: Optional[Dict[str, str]],
                 env_keys: Optional[List[str]],
                 server_command: Optional[List[str]]) -> Dict[str, str]:
    """
    准备环境变量

    优先级：env > env_keys > 自动检测

    Args:
        env: 直接传递的环境变量字典
        env_keys: 要从系统环境变量加载的key列表
        server_command: 服务器命令（用于自动检测）

    Returns:
        合并后的环境变量字典
    """
    result_env = {}

    # 1. 自动检测（优先级最低）
    if server_command:
        # 从命令中提取服务器名称
        server_name = None
        for part in server_command:
            if "server-" in part:
                # 提取类似 "@modelcontextprotocol/server-github" 中的 "server-github"
                server_name = part.split("/")[-1] if "/" in part else part
                break

        # 查找映射表
        if server_name and server_name in MCP_SERVER_ENV_MAP:
            auto_keys = MCP_SERVER_ENV_MAP[server_name]
            for key in auto_keys:
                value = os.getenv(key)
                if value:
                    result_env[key] = value
                    print(f"🔑 自动加载环境变量: {key}")

    # 2. env_keys指定的环境变量（优先级中等）
    if env_keys:
        for key in env_keys:
            value = os.getenv(key)
            if value:
                result_env[key] = value
                print(f"🔑 从env_keys加载环境变量: {key}")
            else:
                print(f"⚠️  警告: 环境变量 {key} 未设置")

    # 3. 直接传递的env（优先级最高）
    if env:
        result_env.update(env)
        for key in env.keys():
            print(f"🔑 使用直接传递的环境变量: {key}")

    return result_env


# 新增：在不同上下文中安全同步运行协程的工具函数
def _run_coroutine_sync(coro):
    """
    在同步上下文中运行协程并返回结果。
    - 如果当前没有运行中的事件循环，直接使用 asyncio.run。
    - 如果已有运行中的事件循环（例如在 uvicorn / jupyter 中），
      则在新线程的新事件循环中运行协程并等待结果。
    """
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # 当前线程有正在运行的事件循环，改为在新线程中运行协程
        result = {}
        def _runner():
            new_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(new_loop)
                res = new_loop.run_until_complete(coro)
                result['value'] = res
            finally:
                try:
                    new_loop.close()
                except Exception:
                    pass
        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        t.join()
        return result.get('value')


# 新增：确保传给 MultiServerMCPClient 的 connections 为 dict 格式（模块级函数）
# 修改：添加 env 参数支持环境变量传递
def _ensure_connections(client_source, env=None):
    """
    将 client_source 规范为 MultiServerMCPClient 期望的连接字典。
    支持输入形式：
      - 已经是 dict：直接返回，但如果提供了env则合并
      - list/tuple（如 ["npx", "-y", "@amap/amap-maps-mcp-server"]）：包装为
          {"<key>": {"command": "npx", "args": ["-y","@amap/..."], "transport": "stdio", "env": env}}
      - str（单一命令）：包装为 {"default": {"command": str, "args": [], "transport": "stdio", "env": env}}
      - 其他对象（如内置 server 实例）：包装为 {"local": {"instance": obj}}
    """
    if client_source is None:
        return {}
    if isinstance(client_source, dict):
        # 如果是字典且提供了env，则添加到每个连接配置中
        if env:
            result = {}
            for k, v in client_source.items():
                if isinstance(v, dict):
                    updated_v = v.copy()
                    updated_v["env"] = env
                    result[k] = updated_v
                else:
                    result[k] = v
            return result
        return client_source

    # 如果是字符串命令
    if isinstance(client_source, str):
        item = {"command": client_source, "args": [], "transport": "stdio"}
        if env:
            item["env"] = env
        return {"default": item}

    # 如果是列表/元组，例如 ["npx", "-y", "@amap/..."]
    if isinstance(client_source, (list, tuple)):
        if len(client_source) == 0:
            return {}
        cmd = client_source[0]
        args = list(client_source[1:]) if len(client_source) > 1 else []
        # 生成 key（尽量基于包名或命令）
        key = "default"
        for part in client_source:
            if isinstance(part, str) and ("server-" in part or "@" in part or "/" in part):
                candidate = part.split("/")[-1]
                candidate = candidate.replace("@", "").replace(".", "_").replace("-", "_")
                if candidate:
                    key = candidate
                    break
        item = {"command": cmd, "args": args, "transport": "stdio"}
        if env:
            item["env"] = env
        return {key: item}

    # 其他对象（例如内置 FastMCP 实例）
    return {"local": {"instance": client_source}}


# 新增：将 StructuredTool / Pydantic 对象 / dict 统一转换为 dict
def _as_tool_dict(t) -> Dict[str, Any]:
    """
    将工具描述规范为 dict：
      - 如果已经是 dict，直接返回（浅拷贝）
      - 如果有 .dict() 方法（pydantic），尝试调用
      - 否则按常见属性提取 name,id,description,server 等字段
      - 最后尝试用 __dict__ 补充剩余字段
    """
    if t is None:
        return {}
    if isinstance(t, dict):
        return dict(t)
    # pydantic model 或其他对象有 dict() 方法
    dict_fn = getattr(t, "dict", None)
    if callable(dict_fn):
        try:
            return dict_fn()
        except Exception:
            pass
    # 提取常见字段
    result = {}
    for attr in ("name", "id", "description", "server", "connection", "connection_name", "server_name", "uri"):
        try:
            val = getattr(t, attr, None)
        except Exception:
            val = None
        if val is not None:
            result[attr] = val
    # 补充 __dict__
    try:
        obj_dict = getattr(t, "__dict__", None)
        if isinstance(obj_dict, dict):
            for k, v in obj_dict.items():
                if k not in result:
                    result[k] = v
    except Exception:
        pass
    return result


class MCPTool(BaseTool):
    """MCP (Model Context Protocol) 工具

       连接到 MCP 服务器并调用其提供的工具、资源和提示词。

       功能：
       - 列出服务器提供的工具
       - 调用服务器工具
       - 读取服务器资源
       - 获取提示词模板

       使用示例:
          from hello_agents.tools.builtin import MCPTool

           # 方式1: 使用内置演示服务器
           tool = MCPTool()  # 自动创建内置服务器
           result = tool.run({"action": "list_tools"})

           # 方式2: 连接到外部 MCP 服务器
           tool = MCPTool(server_command=["python", "examples/mcp_example.py"])
           result = tool.run({"action": "list_tools"})

           # 方式3: 使用自定义 FastMCP 服务器
           from fastmcp import FastMCP
           server = FastMCP("MyServer")
           tool = MCPTool(server=server)
       注意：使用 fastmcp 库，已包含在依赖中
       """
    
    # 定义额外的公共字段
    server_command: Optional[List[str]] = None
    server_args: List[str] = []
    server: Optional[Any] = None
    auto_expand: bool = True
    env: Optional[Dict[str, str]] = None
    prefix: str = ""
    
    # 私有属性
    _client: Optional[Any] = PrivateAttr(default=None)
    _available_tools: List[Any] = PrivateAttr(default_factory=list)

    def __init__(self,
                 name: str = "mcp",
                 description: Optional[str] = None,
                 server_command: Optional[List[str]] = None,
                 server_args: Optional[List[str]] = None,
                 server: Optional[Any] = None,
                 auto_expand: bool = True,
                 env: Optional[Dict[str, str]] = None,
                 env_keys: Optional[List[str]] = None) -> None:
        """
        初始化 MCP 工具

        Args:
            name: 工具名称（默认为"mcp"，建议为不同服务器指定不同名称）
            description: 工具描述（可选，默认为通用描述）
            server_command: 服务器启动命令（如 ["python", "server.py"]）
            server_args: 服务器参数列表
            server: FastMCP 服务器实例（可选，用于内存传输）
            auto_expand: 是否自动展开为独立工具（默认True）
            env: 环境变量字典（优先级最高，直接传递给MCP服务器）
            env_keys: 要从系统环境变量加载的key列表（优先级中等）

        环境变量优先级（从高到低）：
            1. 直接传递的env参数
            2. env_keys指定的环境变量
            3. 自动检测的环境变量（根据server_command）

        注意：如果所有参数都为空，将创建内置演示服务器

        示例：
           # 方式1：直接传递环境变量（优先级最高）
           github_tool = MCPTool(
               name="github",
               server_command=["npx", "-y", "@modelcontextprotocol/server-github"],
               env={"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"}
           )

           # 方式2：从.env文件加载指定的环境变量
           github_tool = MCPTool(
               name="github",
               server_command=["npx", "-y", "@modelcontextprotocol/server-github"],
               env_keys=["GITHUB_PERSONAL_ACCESS_TOKEN"]
           )

           # 方式3：自动检测（最简单，推荐）
           github_tool = MCPTool(
               name="github",
               server_command=["npx", "-y", "@modelcontextprotocol/server-github"]
               # 自动从环境变量加载GITHUB_PERSONAL_ACCESS_TOKEN
           )
        """
        # 调用父类构造函数，先初始化 Pydantic 模型
        # 使用 model_validate 或直接传入字段值
        super().__init__(
            name=name,
            description=description or self._generate_description_template(),
            server_command=server_command,
            server_args=server_args or [],
            server=server,
            auto_expand=auto_expand,
            env=_prepare_env(env, env_keys, server_command),
            prefix=f"{name}_" if auto_expand else ""
        )
        
        # 初始化私有属性
        self._available_tools = []
        
        # 如果没有指定任何服务器，创建内置演示服务器
        if not server_command and not self.server:
            self.server = _create_builtin_server()

        # 自动发现工具
        self._discover_tools()

        # 设置默认描述（如果需要）
        if description is None:
            self.description = self._generate_description()

    def _generate_description_template(self) -> str:
        """生成默认描述模板"""
        return "连接到 MCP 服务器，调用工具、读取资源和获取提示词。支持内置服务器和外部服务器。"

    def _discover_tools(self):
        """发现MCP服务器提供的所有工具"""
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
            import asyncio

            async def discover():
                client_source = self.server if self.server else self.server_command
                # 规范化为 MultiServerMCPClient 期望的 connections dict，并传递环境变量
                client_source = _ensure_connections(client_source, self.env)

                # 不再使用 `async with MultiServerMCPClient(...)`，改为显式创建并在 finally 中关闭
                client = MultiServerMCPClient(client_source)
                try:
                    tools = await client.get_tools()
                    # 将返回的工具对象规范为 dict 列表，避免后续使用 .get 出错
                    tools = [ _as_tool_dict(t) for t in (tools or []) ]
                    return tools
                finally:
                    # 尝试优雅关闭客户端（兼容 aclose/close，同步或异步）
                    aclose = getattr(client, "aclose", None)
                    close = getattr(client, "close", None)
                    try:
                        if callable(aclose):
                            await aclose()
                        elif callable(close):
                            maybe = close()
                            if asyncio.iscoroutine(maybe):
                                await maybe
                    except Exception:
                        # 忽略关闭时的异常
                        pass

            # 运行异步发现（使用统一的同步运行工具，兼容运行中事件循环）
            try:
                self._available_tools = _run_coroutine_sync(discover()) or []
            except Exception:
                # 如果出错，交由外层捕获并打印/处理
                raise

        except Exception as e:
            # 工具发现失败不影响初始化
            print(f"MCP工具发现失败: {str(e)}")
            self._available_tools = []

    def _generate_description(self) -> str:
        """生成增强的工具描述"""
        if not self._available_tools:
            return "连接到 MCP 服务器，调用工具、读取资源和获取提示词。支持内置服务器和外部服务器。"

        if self.auto_expand:
            # 展开模式：简单描述
            return f"MCP工具服务器，包含{len(self._available_tools)}个工具。这些工具会自动展开为独立的工具供Agent使用。"
        else:
            # 非展开模式：详细描述
            desc_parts = [
                f"MCP工具服务器，提供{len(self._available_tools)}个工具："
            ]

            # 列出所有工具
            for tool in self._available_tools:
                tool_name = tool.get('name', 'unknown')
                tool_desc = tool.get('description', '无描述')
                # 简化描述，只取第一句
                short_desc = tool_desc.split('.')[0] if tool_desc else '无描述'
                desc_parts.append(f"  • {tool_name}: {short_desc}")

            # 添加调用格式说明
            desc_parts.append("\n调用格式：返回JSON格式的参数")
            desc_parts.append('{"action": "call_tool", "tool_name": "工具名", "arguments": {...}}')

            # 添加示例
            if self._available_tools:
                first_tool = self._available_tools[0]
                tool_name = first_tool.get('name', 'example')
                desc_parts.append(f'\n示例：{{"action": "call_tool", "tool_name": "{tool_name}", "arguments": {{...}}}}')

            return "\n".join(desc_parts)

    def get_expanded_tools(self) -> List['Tool']:  # type: ignore
        """
        获取展开的工具列表

        将MCP服务器的每个工具包装成独立的Tool对象

        Returns:
            Tool对象列表
        """
        if not self.auto_expand:
            return []

        from .mcp_wrapper_tool import MCPWrappedTool

        expanded_tools = []
        for tool_info in self._available_tools:
            wrapped_tool = MCPWrappedTool(
                mcp_tool=self,
                tool_info=tool_info,
                prefix=self.prefix
            )
            expanded_tools.append(wrapped_tool)

        return expanded_tools

    def _run(self, **kwargs) -> str | None | Any:
        """
        执行 MCP 操作

        Args:
            parameters: 包含以下参数的字典
                - action: 操作类型 (list_tools, call_tool, list_resources, read_resource, list_prompts, get_prompt)
                  如果不指定action但指定了tool_name，会自动推断为call_tool
                - tool_name: 工具名称（call_tool 需要）
                - arguments: 工具参数（call_tool 需要）
                - uri: 资源 URI（read_resource 需要）
                - prompt_name: 提示词名称（get_prompt 需要）
                - prompt_arguments: 提示词参数（get_prompt 可选）

        Returns:
            操作结果
        """
        from langchain_mcp_adapters.client import MultiServerMCPClient
        action = kwargs.get("action", "").lower()
        if not action and "tool_name" in kwargs:
            action = "call_tool"
            kwargs["action"] = action

        if not action:
            return "错误：必须指定 action 参数或 tool_name 参数"
        try:
            # 使用增强的异步客户端
            import asyncio
            from langchain_mcp_adapters.client import MultiServerMCPClient

            async def run_mcp_operation():
                # 根据配置选择客户端创建方式
                if self.server:
                    # 使用内置服务器（内存传输）
                    client_source = self.server
                else:
                    # 使用外部服务器命令
                    client_source = self.server_command

                # 规范化为 MultiServerMCPClient 期望的 connections dict，并传递环境变量
                client_source = _ensure_connections(client_source, self.env)

                # 不再使用 async with，改为显式创建并在 finally 中关闭
                client = MultiServerMCPClient(client_source)
                try:
                    if action == "list_tools":
                        tools = await client.get_tools()
                        if not tools:
                            return "没有找到可用的工具"
                        # 规范化工具对象为 dict 列表
                        tools = [ _as_tool_dict(t) for t in (tools or []) ]
                        result = f"找到 {len(tools)} 个工具:\n"
                        for tool in tools:
                            result += f"- {tool.get('name')}: {tool.get('description')}\n"
                        return result

                    elif action == "list_resources":
                        resources = await client.get_resources()
                        if not resources:
                            return "没有找到可用的资源"
                        result = f"找到 {len(resources)} 个资源:\n"
                        for resource in resources:
                            result += f"- {resource['uri']}: {resource['name']}\n"
                        return result

                    elif action == "get_prompt":
                        prompt_name = kwargs.get("prompt_name")
                        prompt_arguments = kwargs.get("prompt_arguments", {})
                        if not prompt_name:
                            return "错误：必须指定 prompt_name 参数"
                        messages = await client.get_prompt(prompt_name, prompt_arguments)
                        result = f"提示词 '{prompt_name}':\n"
                        for msg in messages:
                            result += f"[{msg['role']}] {msg['content']}\n"
                        return result

                    elif action == "call_tool":
                        tool_name = kwargs.get("tool_name")
                        arguments = kwargs.get("arguments", {})
                        if not tool_name:
                            return "错误：必须指定 tool_name 参数"
                        
                        # 调用工具 - 优先使用 client 提供的快捷方法，其次尝试通过会话(session)或通用请求调用
                        try:
                            # 1) 直接尝试 client 层的便捷方法
                            if hasattr(client, "run_tool"):
                                return await client.run_tool(tool_name, arguments)
                            if hasattr(client, "call_tool"):
                                return await client.call_tool(tool_name, arguments)

                            # 2) 如果没有直接方法，先尝试从 get_tools 中定位工具并获取其所在的 server/connection
                            tools_list = await client.get_tools()
                            # 规范化工具对象为 dict 列表，避免 StructuredTool 无法用 .get 访问
                            tools_list = [ _as_tool_dict(t) for t in (tools_list or []) ]

                            tool_info = None
                            if tools_list:
                                tool_info = next((t for t in tools_list if (t.get("name") == tool_name or t.get("id") == tool_name)), None)

                            candidate_servers = []
                            if tool_info:
                                # 尝试多种可能的字段名
                                server_name = tool_info.get("server") or tool_info.get("connection") or tool_info.get("connection_name") or tool_info.get("server_name")
                                if server_name:
                                    candidate_servers.append(server_name)

                            # 如果未从工具信息中找到 server，降级为遍历 client.connections
                            connections = getattr(client, "connections", None) or {}
                            if not candidate_servers:
                                candidate_servers = list(connections.keys()) if isinstance(connections, dict) else []

                            last_exc = None
                            # 遍历候选服务器并尝试在各自会话中调用工具
                            for server in candidate_servers:
                                try:
                                    async with client.session(server) as session:
                                        # 优先使用 session 层的便捷方法
                                        if hasattr(session, "run_tool"):
                                            return await session.run_tool(tool_name, arguments)
                                        if hasattr(session, "call_tool"):
                                            return await session.call_tool(tool_name, arguments)
                                        # 通用请求方式（MCP RPC）
                                        try:
                                            resp = await session.send_request({
                                                "method": "tools/call",
                                                "params": {"name": tool_name, "arguments": arguments}
                                            })
                                            return resp
                                        except Exception as e:
                                            # 如果单个 session 调用失败，记录并继续尝试下一个
                                            last_exc = e
                                            continue
                                except Exception as e:
                                    last_exc = e
                                    continue

                            # 如果所有尝试都失败，抛出最后一个异常或返回错误信息
                            if last_exc:
                                raise last_exc
                            else:
                                raise RuntimeError("未能找到可用的服务器来执行工具调用")
                        except Exception as e:
                            # 将错误向上抛出，由外层 finally 做关闭处理
                            raise

                    else:
                        return f"错误：不支持的操作 '{action}'"
                finally:
                    # 尝试优雅关闭客户端（兼容 aclose/close，同步或异步）
                    aclose = getattr(client, "aclose", None)
                    close = getattr(client, "close", None)
                    try:
                        if callable(aclose):
                            await aclose()
                        elif callable(close):
                            maybe = close()
                            if asyncio.iscoroutine(maybe):
                                await maybe
                    except Exception:
                        pass

            # 运行异步操作：使用统一的同步运行工具，确保协程被执行（无论当前是否有运行的事件循环）
            try:
                result = _run_coroutine_sync(run_mcp_operation())
                return result
            except Exception as e:
                print(f"MCP异步操作异常: {str(e)}")
                return f"异步操作失败: {str(e)}"

        except Exception as e:
            return f"MCP 操作失败: {str(e)}"

    async def _arun(self, **kwargs):
        """
        异步执行 MCP 操作
        """
        from langchain_mcp_adapters.client import MultiServerMCPClient
        action = kwargs.get("action", "").lower()
        if not action and "tool_name" in kwargs:
            action = "call_tool"
            kwargs["action"] = action

        if not action:
            return "错误：必须指定 action 参数或 tool_name 参数"
        
        try:
            import asyncio
            from langchain_mcp_adapters.client import MultiServerMCPClient

            # 根据配置选择客户端创建方式
            if self.server:
                # 使用内置服务器（内存传输）
                client_source = self.server
            else:
                # 使用外部服务器命令
                client_source = self.server_command

            # 显式创建客户端并在 finally 中关闭（使用模块级 _ensure_connections 并传递环境变量）
            client = MultiServerMCPClient(_ensure_connections(client_source, self.env))
            try:
                if action == "list_tools":
                    tools = await client.get_tools()
                    if not tools:
                        return "没有找到可用的工具"
                    # 规范化工具对象为 dict 列表
                    tools = [ _as_tool_dict(t) for t in (tools or []) ]
                    result = f"找到 {len(tools)} 个工具:\n"
                    for tool in tools:
                        result += f"- {tool.get('name')}: {tool.get('description')}\n"
                    return result

                elif action == "list_resources":
                    resources = await client.get_resources()
                    if not resources:
                        return "没有找到可用的资源"
                    result = f"找到 {len(resources)} 个资源:\n"
                    for resource in resources:
                        result += f"- {resource['uri']}: {resource['name']}\n"
                    return result

                elif action == "get_prompt":
                    prompt_name = kwargs.get("prompt_name")
                    prompt_arguments = kwargs.get("prompt_arguments", {})
                    if not prompt_name:
                        return "错误：必须指定 prompt_name 参数"
                    messages = await client.get_prompt(prompt_name, prompt_arguments)
                    result = f"提示词 '{prompt_name}':\n"
                    for msg in messages:
                        result += f"[{msg['role']}] {msg['content']}\n"
                    return result

                elif action == "call_tool":
                    tool_name = kwargs.get("tool_name")
                    arguments = kwargs.get("arguments", {})
                    if not tool_name:
                        return "错误：必须指定 tool_name 参数"
                    
                    # 调用工具 - 优先使用 client 提供的快捷方法，其次尝试通过会话(session)或通用请求调用
                    try:
                        if hasattr(client, "run_tool"):
                            return await client.run_tool(tool_name, arguments)
                        if hasattr(client, "call_tool"):
                            return await client.call_tool(tool_name, arguments)

                        tools_list = await client.get_tools()
                        # 规范化工具对象为 dict 列表，避免 StructuredTool 无法用 .get 访问
                        tools_list = [ _as_tool_dict(t) for t in (tools_list or []) ]

                        tool_info = None
                        if tools_list:
                            tool_info = next((t for t in tools_list if t.get("name") == tool_name or t.get("id") == tool_name), None)

                        candidate_servers = []
                        if tool_info:
                            server_name = tool_info.get("server") or tool_info.get("connection") or tool_info.get("connection_name") or tool_info.get("server_name")
                            if server_name:
                                candidate_servers.append(server_name)

                        connections = getattr(client, "connections", None) or {}
                        if not candidate_servers:
                            candidate_servers = list(connections.keys()) if isinstance(connections, dict) else []

                        last_exc = None
                        for server in candidate_servers:
                            try:
                                async with client.session(server) as session:
                                    if hasattr(session, "run_tool"):
                                        return await session.run_tool(tool_name, arguments)
                                    if hasattr(session, "call_tool"):
                                        return await session.call_tool(tool_name, arguments)
                                    try:
                                        resp = await session.send_request({
                                            "method": "tools/call",
                                            "params": {"name": tool_name, "arguments": arguments}
                                        })
                                        return resp
                                    except Exception as e:
                                        last_exc = e
                                        continue
                            except Exception as e:
                                last_exc = e
                                continue

                        if last_exc:
                            raise last_exc
                        else:
                            raise RuntimeError("未能找到可用的服务器来执行工具调用")
                    except Exception as e:
                        # 将异常向上传递，由上层捕获并返回友好错误信息
                        raise

                else:
                    return f"错误：不支持的操作 '{action}'"
            finally:
                # 尝试优雅关闭客户端（兼容 aclose/close，同步或异步）
                aclose = getattr(client, "aclose", None)
                close = getattr(client, "close", None)
                try:
                    if callable(aclose):
                        await aclose()
                    elif callable(close):
                        maybe = close()
                        if asyncio.iscoroutine(maybe):
                            await maybe
                except Exception:
                    pass

        except Exception as e:
            return f"MCP 异步操作失败: {str(e)}"

    def get_parameters(self) -> List[ToolParameter]:
        """获取工具参数定义"""
        return [
            ToolParameter(
                name="action",
                type="string",
                description="操作类型: list_tools, call_tool, list_resources, read_resource, list_prompts, get_prompt",
                required=True
            ),
            ToolParameter(
                name="tool_name",
                type="string",
                description="工具名称（call_tool 操作需要）",
                required=False
            ),
            ToolParameter(
                name="arguments",
                type="object",
                description="工具参数（call_tool 操作需要）",
                required=False
            ),
            ToolParameter(
                name="uri",
                type="string",
                description="资源 URI（read_resource 操作需要）",
                required=False
            ),
            ToolParameter(
                name="prompt_name",
                type="string",
                description="提示词名称（get_prompt 操作需要）",
                required=False
            ),
            ToolParameter(
                name="prompt_arguments",
                type="object",
                description="提示词参数（get_prompt 操作可选）",
                required=False
            )
        ]
