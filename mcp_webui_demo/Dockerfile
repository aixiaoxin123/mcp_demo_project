FROM python:3.10-slim

# 创建 APT 源列表文件并使用中科大的镜像源
RUN echo "deb https://mirrors.ustc.edu.cn/debian/ bullseye main contrib non-free" > /etc/apt/sources.list && \
    echo "deb-src https://mirrors.ustc.edu.cn/debian/ bullseye main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.ustc.edu.cn/debian-security/ bullseye/updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb-src https://mirrors.ustc.edu.cn/debian-security/ bullseye/updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.ustc.edu.cn/debian/ bullseye-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb-src https://mirrors.ustc.edu.cn/debian/ bullseye-updates main contrib non-free" >> /etc/apt/sources.list

# 设置 PIP 国内源
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/

# 更新包列表并安装依赖 + uv + dotenv
RUN apt-get update && apt-get install -y \
    curl build-essential git && \
    pip install --upgrade pip && \
    pip install uv python-dotenv && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 拷贝项目代码（不包括挂载配置）
COPY . .

# 使用 uv 安装依赖
RUN uv pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple/

# 开放端口
EXPOSE 7860

# 启动 WebUI
CMD ["uv", "run", "webui_deepseek.py"]
