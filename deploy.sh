#如果你想彻底关闭并删除这个容器，比如你要部署一个全新的版本（就像你的 deploy.sh 脚本做的那样），你需要两步操作：停止，然后移除。

# # 第1步：停止容器（如果它正在运行）
# docker stop jfrog-automation-server-prod

# # 第2步：移除已停止的容器
# docker rm jfrog-automation-server-prod
# 移除之后，这个容器就彻底消失了。你无法再 start 它。如果你想再次运行服务，就必须执行 ./deploy.sh 重新 docker run 一个全新的容器。
#!/bin/bash

# 定义镜像和容器名称
IMAGE_NAME="jfrog-automation-server"
TAG="latest"
CONTAINER_NAME="jfrog-automation-server-prod" # 使用一个生产环境的容器名

# 颜色输出
GREEN='\033[0;32m'
NC='\033[0m'

echo -e "${GREEN}Step 1: Building the Docker image...${NC}"
docker build -t ${IMAGE_NAME}:${TAG} .

if [ $? -ne 0 ]; then
    echo "Error: Docker image build failed."
    exit 1
fi

echo -e "\n${GREEN}Step 2: Stopping and removing any old production container...${NC}"
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

echo -e "\n${GREEN}Step 3: Running the new container in PRODUCTION mode...${NC}"
# --- 核心修改在这里 ---
# 1. 使用 -d 参数，让容器在后台运行
# 2. 使用 --restart always 策略，当容器退出时（无论是崩溃还是服务器重启），Docker 会自动重启它
# 3. 端口映射保持不变
docker run -d \
    --restart always \
    -p 8000:8000 \
    --name ${CONTAINER_NAME} \
    --env-file .env \
    ${IMAGE_NAME}:${TAG}

echo -e "\n${GREEN}Success! The service is now running in the background.${NC}"
echo "You can check its status with: docker ps"
echo "You can view its logs with: docker logs -f ${CONTAINER_NAME}"