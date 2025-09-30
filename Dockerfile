FROM artifactory.momenta.works/docker-momenta/python:3.10
# 设置工作目录，后续的命令都会在这个目录下执行
WORKDIR /app

# 将依赖文件复制到镜像中
# 我们先复制这个文件，是为了利用 Docker 的缓存机制。
# 只要 requirements.txt 不变，下面这层就不会重新构建，可以加快后续的构建速度。
COPY requirements.txt .

# 在镜像中安装项目的 Python 依赖
# --no-cache-dir 选项可以减小镜像体积
RUN pip install --no-cache-dir -r requirements.txt

# 将项目的所有文件（.py, .env 等）复制到镜像的 /app 目录下
COPY . .

# 暴露端口
# 告诉 Docker，容器内的 8000 端口需要被外部访问
# 这只是一个声明，实际的端口映射在 `docker run` 命令中指定
EXPOSE 8000

# 容器启动时要执行的命令
# 使用 uvicorn 启动 FastAPI 应用
# --host 0.0.0.0 是关键，它让服务监听所有网络接口，而不仅仅是 localhost，
# 这样我们才能从容器外部访问它。
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]