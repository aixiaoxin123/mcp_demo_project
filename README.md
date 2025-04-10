# 参考教程：
https://mcp-docs.cn/introduction



# 下载代码


git clone  https://github.com/aixiaoxin123/mcp_demo_project.git

# 进入代码目录
cd mcp_demo_project




# 创建conda环境

conda create -n mcp_demo  python=3.10

conda activate mcp_demo

# 安装uv 工具
pip install uv  -i https://pypi.tuna.tsinghua.edu.cn/simple/

uv --version





# 利用uv 在当前目录，创建一个虚拟环境
uv venv

# 激活虚拟环境
# linux 下命令
source .venv/bin/activate
# windows 下命令
.venv\Scripts\activate




# uv 安装对应的依赖包
uv pip install mcp  mcp[cli]  anthropic  openai   httpx  -i https://pypi.tuna.tsinghua.edu.cn/simple/ 




# 启动mcp服务





## 运行 客户端和本地服务端

###   配置.env 文件，填入你的密钥


### 利用deepseek大模型进行问答

uv run client_deepseek.py   weather_server.py

### 利用qwen大模型进行问答

uv run client_qwen.py   weather_server.py

### 利用openai模型进行问答

uv run client_openai.py   weather_server.py



## 也可以单独运行 mcp服务端，用于提供给互联网环境使用

uv run  mcp dev weather_server.py
