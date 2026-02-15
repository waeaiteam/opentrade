FROM python:3.11-slim

WORKDIR /root

# 安装依赖
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]"

# 复制应用
COPY opentrade/ ./opentrade/

# 创建数据目录
RUN mkdir -p /root/.opentrade/data /root/.opentrade/logs

# 默认命令
CMD ["opentrade", "gateway"]
