#!/bin/bash
#python -m uvicorn main:app --reload

# 定义镜像和容器名称
IMAGE_NAME="jfrog-automation-server"
TAG="latest"
CONTAINER_NAME="jfrog-automation-server-dev" # 使用一个不同的容器名，避免和生产冲突

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Step 1: Building the Docker image (if necessary)...${NC}"
docker build -t ${IMAGE_NAME}:${TAG} .

if [ $? -ne 0 ]; then
    echo "Error: Docker image build failed."
    exit 1
fi

echo -e "\n${GREEN}Step 2: Stopping and removing any old development container...${NC}"
# 查找并停止同名的旧容器
docker stop ${CONTAINER_NAME} 2>/dev/null || true
docker rm ${CONTAINER_NAME} 2>/dev/null || true

echo -e "\n${GREEN}Step 3: Running the new container in INTERACTIVE/DEBUG mode...${NC}"
echo -e "${YELLOW}All logs will be printed here in real-time. Press CTRL+C to stop.${NC}\n"

# --- 核心修改在这里 ---
# 1. 去掉了 -d 参数，让容器在前台运行
# 2. 增加了 --rm 参数，这样当容器停止时（比如你按 CTRL+C），它会被自动删除，保持环境干净
# 3. 容器名改为 ${CONTAINER_NAME}
docker run --rm \
    -p 8443:8443 \
    --name ${CONTAINER_NAME} \
    --env-file .env \
    ${IMAGE_NAME}:${TAG}

# 当你按 CTRL+C 停止上面的 docker run 命令后，脚本会继续执行到这里
echo -e "\n\n${YELLOW}Container stopped and removed. Script finished.${NC}"