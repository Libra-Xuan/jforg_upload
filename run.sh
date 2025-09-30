#!/bin/bash

# 定义镜像名称和标签
IMAGE_NAME="jfrog-automation-server"
IMAGE_TAG="latest"

# 脚本的颜色输出，方便查看
GREEN='\033[0;32m'
NC='\033[0m' # No Color

echo -e "${GREEN}Step 1: Building the Docker image...${NC}"
# 使用当前目录的 Dockerfile 来构建镜像
# -t 参数用于给镜像命名和打标签 (name:tag)
docker build -t ${IMAGE_NAME}:${IMAGE_TAG} .

# 检查上一步命令是否成功
if [ $? -ne 0 ]; then
    echo "Error: Docker image build failed."
    exit 1
fi

echo -e "\n${GREEN}Step 2: Checking for and stopping any old running container...${NC}"
# 查找并停止同名的旧容器，避免端口冲突
docker stop ${IMAGE_NAME} 2>/dev/null || true
docker rm ${IMAGE_NAME} 2>/dev/null || true

echo -e "\n${GREEN}Step 3: Running the new Docker container...${NC}"
# 运行新的容器
# -d: 在后台（detached mode）运行容器
# -p 8000:8000: 将主机的 8000 端口映射到容器的 8000 端口
#    (前面的 8000 是主机的端口，后面的 8000 是容器的端口)
# --name: 给这个运行的容器起一个名字，方便管理
# --env-file .env: 将 .env 文件中的所有环境变量注入到容器中，这是最关键的一步，
#                 这样你的代码在容器内也能读到 EP_API_TOKEN
docker run -d \
    -p 8000:8000 \
    --name ${IMAGE_NAME} \
    --env-file .env \
    ${IMAGE_NAME}:${IMAGE_TAG}

# 检查容器是否成功启动
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}Success! The service is running in a Docker container.${NC}"
    echo "You can access the service via http://127.0.0.1:8000"
    echo "To see the logs, run: docker logs -f ${IMAGE_NAME}"
    echo "To stop the service, run: docker stop ${IMAGE_NAME}"
else
    echo "Error: Failed to run the Docker container."
fi
