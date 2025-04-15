import asyncio
from typing import Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from dotenv import load_dotenv
import os
load_dotenv()  # load environment variables from .env

from openai import OpenAI
import json

api_key = os.environ["QWEN_API_KEY"]
base_url = os.environ["QWEN_API_BASE"]

model_type=os.environ["QWEN_MODEL"]


print(api_key)
print(base_url)


class MCPClient:
    def __init__(self):
        # Initialize session and client objects
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.anthropic = OpenAI(api_key=api_key, base_url=base_url)

        # api_key=os.environ.get("ANTHROPIC_API_KEY")
        # api_base=os.environ.get("ANTHROPIC_API_KEY")
    # methods will go here


    async def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server

        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")

        command = "python" if is_python else "node"
        server_params = StdioServerParameters(
            command=command,
            args=[server_script_path],
            env=None
        )

        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))

        await self.session.initialize()

        # List available tools
        response = await self.session.list_tools()
        tools = response.tools
        print("\nConnected to server with tools:", [tool.name for tool in tools])




    
    async def connect_to_sse_server(self, server_url: str):
        """Connect to an MCP server running with SSE transport"""
        # 创建 SSE 客户端连接上下文管理器
        self._streams_context = sse_client(url=server_url)
        # 异步初始化 SSE 连接，获取数据流对象
        streams = await self._streams_context.__aenter__()

        # 使用数据流创建 MCP 客户端会话上下文
        self._session_context = ClientSession(*streams)
        # 初始化客户端会话对象
        self.session: ClientSession = await self._session_context.__aenter__()

        # 执行 MCP 协议初始化握手
        await self.session.initialize()



    async def process_query(self, query: str) -> str:
        """Process a query using Claude and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        response = await self.session.list_tools()


        available_tools = []

        for tool in response.tools:
            tool_schema = getattr(
                tool,
                "inputSchema",
                {"type": "object", "properties": {}, "required": []},
            )

            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool_schema,
                },
            }
            available_tools.append(openai_tool)

        # Initial Claude API call
        model_response = self.anthropic.chat.completions.create(
            model=model_type,
            max_tokens=1000,
            messages=messages,
            tools=available_tools,
        )

        # Process response and handle tool calls
        final_text = []
        tool_results = []

        messages.append(model_response.choices[0].message.model_dump())
        print(messages[-1])
        if model_response.choices[0].message.tool_calls:
            tool_call = model_response.choices[0].message.tool_calls[0]
            tool_args = json.loads(tool_call.function.arguments)

            tool_name = tool_call.function.name
            result = await self.session.call_tool(tool_name, tool_args)
            tool_results.append({"call": tool_name, "result": result})
            final_text.append(f"[Calling tool {tool_name} with args {tool_args}]")

            messages.append(
                {
                    "role": "tool",
                    "content": f"{result}",
                    "tool_call_id": tool_call.id,
                }
            )

            # Get next response from Claude
            response = self.anthropic.chat.completions.create(
                model=model_type,
                max_tokens=1000,
                messages=messages,
            )

            messages.append(response.choices[0].message.model_dump())
            print(messages[-1])

        return messages[-1]["content"]



    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        print("\n🤖 MCP 客户端已启动！输入 'quit' 退出")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == 'quit':
                    break

                response = await self.process_query(query)
                print("\n" + response)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def cleanup(self):
        """Clean up resources"""
        await self.exit_stack.aclose()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <path_to_server_script>")
        sys.exit(1)

    print("Connecting to server...")
    print(sys.argv)
    client = MCPClient()
    try:
        await client.connect_to_sse_server(sys.argv[1])
        await client.chat_loop()
    finally:
        await client.cleanup()

if __name__ == "__main__":
    import sys
    asyncio.run(main())