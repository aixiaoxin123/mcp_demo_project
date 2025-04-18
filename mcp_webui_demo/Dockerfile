FROM python:3.10.13-slim-bookworm

# 打印系统版本确认是 bookworm
RUN cat /etc/os-release



RUN test -e /etc/apt/sources.list || echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free" > /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free" >> /etc/apt/sources.list



# 设置 PIP 国内源
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

# 安装系统依赖、uv、dotenv
# 更新包列表并安装必要的包
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    # 安装你需要的其他包
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip && \
    pip install uv python-dotenv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 拷贝项目代码（不包括 .env 和 mcp.json）
COPY . .

# 使用 uv 安装依赖
RUN uv pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple/

# 开放端口
EXPOSE 7860

# 启动 WebUI
CMD ["uv", "run", "webui_deepseek.py"]
