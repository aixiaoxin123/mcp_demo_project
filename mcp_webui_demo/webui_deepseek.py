import asyncio
import gradio as gr
from typing import Optional
from contextlib import AsyncExitStack
import json
import os
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

curr_dir = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(curr_dir, "mcp.json")
ENV_PATH = ".env"

load_dotenv()

from openai import OpenAI

api_key = os.environ["DEEPSEEK_API_KEY"]
base_url = os.environ["DEEPSEEK_API_BASE"]
model_type = os.environ["DEEPSEEK_MODEL"]


class MCPClient:
    def __init__(self):
        self.session: Optional[object] = None
        self.exit_stack = AsyncExitStack()
        self.sessions = {}
        self.tools_map = {}
        self.openai_client = OpenAI(api_key=api_key, base_url=base_url)

    async def connect_to_sse_server_by_config(self, config_path: str = CONFIG_PATH):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)

            if 'mcpServers' not in config:
                raise ValueError("服务端配置文件中缺少 mcpServers 字段")

            mcp_servers = config['mcpServers']
            connect_tasks = []
            for server_id, server_info in mcp_servers.items():
                if 'url' not in server_info:
                    print(f"警告: 服务器 {server_id} 缺少 url 配置，跳过")
                    continue
                connect_tasks.append(self._connect_single_sse_server(server_id, server_info))

            results = await asyncio.gather(*connect_tasks, return_exceptions=True)
            success_count = sum(1 for r in results if not isinstance(r, Exception))
            print(f"\n成功连接 {success_count} 个SSE服务器 (共尝试 {len(connect_tasks)} 个)")
            if self.sessions:
                await self.list_tools()
            else:
                print("警告: 没有成功连接任何服务器")
        except FileNotFoundError:
            print(f"错误: 服务端配置文件 {config_path} 不存在")
        except json.JSONDecodeError:
            print(f"错误: 服务端配置文件 {config_path} 不是有效的JSON格式")
        except Exception as e:
            print(f"连接SSE服务器时发生错误: {str(e)}")

    async def _connect_single_sse_server(self, server_id: str, server_info: dict):
        try:
            server_url = server_info['url']
            # streams_context = sse_client(url=server_url)
            # streams = await streams_context.__aenter__()
            # session_context = ClientSession(*streams)
            # session = await session_context.__aenter__()

            # 修改后的
            streams = await self.exit_stack.enter_async_context(sse_client(url=server_url))
            session = await self.exit_stack.enter_async_context(ClientSession(*streams))

            await session.initialize()
            self.sessions[server_id] = {
                "session": session,
                "url": server_url
            }
            response = await session.list_tools()
            for tool in response.tools:
                self.tools_map[tool.name] = server_id
            print(f"成功连接到服务器 {server_id} ({server_url})")
        except Exception as e:
            print(f"连接服务器 {server_id} 失败: {str(e)}")
            raise

    async def list_tools(self):
        if not self.sessions:
            print("没有已连接的服务端")
            return
        print("已连接的服务端列表:")
        for server_id, session_info in self.sessions.items():
            print(f"服务端: {server_id}, URL: {session_info['url']}")

    async def process_query(self, query: str, update_output: callable):
        messages = [{"role": "user", "content": query}]

        async def log(text):
            await update_output(text + "\n")
            print(text)

        await log(f"🔵 开始处理查询: {query}")

        available_tools = []
        for tool_name, server_id in self.tools_map.items():
            session = self.sessions[server_id]["session"]
            response = await session.list_tools()
            for tool in response.tools:
                if tool.name == tool_name:
                    available_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema
                        }
                    })

        await log(f"🛠️ 可用工具列表:\n{json.dumps(available_tools, indent=2, ensure_ascii=False)}")

        await log("🤖 正在调用模型API进行初始分析...")
        model_response = self.openai_client.chat.completions.create(
            model=model_type,
            max_tokens=1000,
            messages=messages,
            tools=available_tools if available_tools else None
        )
        assistant_message = model_response.choices[0].message
        messages.append(assistant_message.model_dump())

        await log(f"💡 模型初始响应:\n{json.dumps(assistant_message.model_dump(), indent=2, ensure_ascii=False)}")

        if assistant_message.tool_calls:
            for tool_call in assistant_message.tool_calls:
                await log(f"🔧 准备调用工具: {tool_call}")
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                await log(f"⚙️ 准备调用工具: {tool_name}")
                await log(f"📋 工具参数:\n{json.dumps(tool_args, indent=2, ensure_ascii=False)}")

                server_id = self.tools_map[tool_name]
                session = self.sessions[server_id]["session"]

                await log(f"🔗 连接到服务器: {server_id}")
                try:
                    await log("🔄 正在执行工具调用...")
                    result = await session.call_tool(tool_name, tool_args)
                    await log(f"✅ 工具调用成功! 结果:\n{result}")
                    
                    messages.append({
                        "role": "tool",
                        "content": f"{result}",
                        "tool_call_id": tool_call.id,
                        "name": tool_name
                    })
                except Exception as e:
                    error_msg = f"❌ 工具调用失败: {str(e)}"
                    await log(error_msg)
                    messages.append({
                        "role": "tool",
                        "content": error_msg,
                        "tool_call_id": tool_call.id,
                        "name": tool_name
                    })

            await log("\n🔄 正在获取模型最终响应...")
            final_response = self.openai_client.chat.completions.create(
                model=model_type,
                max_tokens=1000,
                messages=messages,
            )
            final_message = final_response.choices[0].message
            messages.append(final_message.model_dump())
            await log(f"✨ 最终响应:\n{final_message.content}")
            
            return final_message.content

        await log("📝 模型直接返回结果:")
        return assistant_message.content

    async def cleanup(self):
        await self.exit_stack.aclose()



    async def disconnect_all(self):
        try:
            await self.exit_stack.aclose()  # 自动清理所有 context
            self.exit_stack = AsyncExitStack()  # 重置
            self.sessions = {}
            self.tools_map = {}
            print("✅ 所有服务器连接已断开")
            return "✅ 所有服务器连接已断开"
        except Exception as e:
            error_msg = f"❌ 清理上下文出错: {str(e)}"
            print(error_msg)
            return error_msg





client = MCPClient()


async def gradio_interface(query: str):
    output_queue = asyncio.Queue()
    full_output = ""

    async def update_output(new_text: str):
        await output_queue.put(new_text)

    if not client.sessions:
        await client.connect_to_sse_server_by_config()

    process_task = asyncio.create_task(client.process_query(query, update_output))
    get_output_task = asyncio.create_task(output_queue.get())

    yield full_output, "⏳ 正在生成回答..."

    try:
        while True:
            done, _ = await asyncio.wait(
                [get_output_task, process_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            if get_output_task in done:
                new_text = get_output_task.result()
                full_output += new_text
                yield full_output, "⏳ 正在生成回答..."
                get_output_task = asyncio.create_task(output_queue.get())

            if process_task in done:
                if not process_task.cancelled():
                    result = await process_task
                    full_output += f"\n\n✅ 处理完成:\n{result}"
                    yield full_output, "✅ 回答完成"
                break

    except Exception as e:
        full_output += f"\n❌ 发生错误: {str(e)}"
        yield full_output, f"❌ 错误: {str(e)}"
    finally:
        if not process_task.done():
            process_task.cancel()





#新增的
async def connect_servers():
    await client.connect_to_sse_server_by_config()
    return "✅ 已尝试连接所有服务端"

async def disconnect_servers():
    await client.disconnect_all()
    return "✅ 所有服务端连接已断开"

async def get_tool_list_display():
    try:
        if not client.sessions:
            return "⚠️ 当前未连接任何服务端"
        display = []
        for server_id, session_info in client.sessions.items():
            display.append(f"### 🔌 服务端：`{server_id}` ({session_info['url']})")
            session = session_info["session"]
            try:
                response = await session.list_tools()
                for tool in response.tools:
                    display.append(f"- 🛠️ **{tool.name}**: {tool.description}")
            except Exception as e:
                display.append(f"⚠️ 无法列出工具: {str(e)}")
            display.append("\n")
        return "\n".join(display)
    except Exception as e:
        return f"❌ 工具列表刷新失败: {str(e)}"



def load_config_file():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return "{}"

def save_config_file(content: str):
    try:
        json.loads(content)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print("✅ 服务端配置文件保存成功！")
        return "✅ 服务端配置文件保存成功！"
    except json.JSONDecodeError:
        print("❌ 保存失败：无效的 JSON 格式")
        return "❌ 保存失败：无效的 JSON 格式"
    except Exception as e:
        print(f"❌ 保存失败：{str(e)}")
        return f"❌ 保存失败：{str(e)}"

def load_env_file():
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def save_env_file(content: str):
    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        return "✅ 环境变量文件保存成功！"
    except Exception as e:
        return f"❌ 保存失败：{str(e)}"



with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🛠️ MCP 客户端工具调用演示---author : AI小新")

    with gr.Tab("💬 主界面"):
        with gr.Row():
            input_text = gr.Textbox(label="输入查询", placeholder="请输入您的问题...", lines=3)
        with gr.Row():
            submit_btn = gr.Button("开始问答", variant="primary")
        with gr.Row():
            status_box = gr.Textbox(label="问答状态", value="", interactive=False)
        with gr.Row():
            output_text = gr.Textbox(label="问答过程", interactive=False, lines=20, autoscroll=True)

        

    with gr.Tab("⚙️ 服务端配置文件"):
        gr.Markdown("### 编辑 mcp.json 服务端配置文件")
        config_editor = gr.Code(value=load_config_file(), language="json", lines=20)
        save_config_btn = gr.Button("保存配置", variant="secondary")
        config_status = gr.Textbox(label="状态", interactive=False)

    # with gr.Tab("🔑 环境变量"):
    #     gr.Markdown("### 编辑 .env 文件")
    #     env_editor = gr.Code(value=load_env_file(), language="python", lines=10)
    #     save_env_btn = gr.Button("保存环境变量", variant="secondary")
    #     env_status = gr.Textbox(label="状态", interactive=False)

    with gr.Tab("🔗 服务端控制"):
        gr.Markdown("### 连接和断开 SSE 服务器")
        connect_btn = gr.Button("🔌 连接所有服务端", variant="primary")
        disconnect_btn = gr.Button("❌ 断开所有服务端", variant="stop")
        connect_status = gr.Textbox(label="连接状态", interactive=False)

    with gr.Tab("📦 可用工具列表"):
        gr.Markdown("### 当前已连接服务端的工具清单")
        refresh_tools_btn = gr.Button("🔄 刷新工具列表")
        tools_display = gr.Markdown("点击上方按钮查看可用工具")


    gr.Markdown("# github 开源地址： https://github.com/aixiaoxin123/mcp_demo_project ")

    # 新增的    
    connect_servers()
    # 绑定事件

    submit_btn.click(gradio_interface, inputs=[input_text], outputs=[output_text, status_box])
    save_config_btn.click(save_config_file, inputs=[config_editor], outputs=[config_status])
    # save_env_btn.click(save_env_file, inputs=[env_editor], outputs=[env_status])
    connect_btn.click(connect_servers, outputs=[connect_status])
    disconnect_btn.click(disconnect_servers, outputs=[connect_status])

    refresh_tools_btn.click(get_tool_list_display, outputs=[tools_display])


if __name__ == "__main__":

    demo.launch(debug=True, share=False, inbrowser=True, server_name="0.0.0.0")