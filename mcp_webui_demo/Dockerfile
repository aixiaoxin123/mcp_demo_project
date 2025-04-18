FROM python:3.10-slim

ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

RUN apt-get update && apt-get install -y \
    curl build-essential git && \
    pip install --upgrade pip && \
    pip install uv python-dotenv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 拷贝代码（不拷贝 .env 和 mcp.json，准备挂载）
COPY . .

# 安装依赖
RUN uv pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple/

# 显式暴露端口
EXPOSE 7860

# 启动 webui
CMD ["uv", "run", "webui_deepseek.py"]