#!/bin/bash
# AI Techne Academy - Push Processor Image to ECR
# This script pushes the processor container image to AWS ECR

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="ai-techne-processor"
ECR_REPO_NAME="ai-techne-academy/processor"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo -e "${YELLOW}=====================================${NC}"
echo -e "${YELLOW}AI Techne Academy - Push to ECR${NC}"
echo -e "${YELLOW}=====================================${NC}"
echo ""

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}Error: AWS CLI is not installed${NC}"
    echo "Please install AWS CLI: https://aws.amazon.com/cli/"
    exit 1
fi

echo -e "${GREEN}✓${NC} AWS CLI is installed"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker is running"

# Get AWS Account ID
echo ""
echo -e "${BLUE}Getting AWS Account ID...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)

if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}Error: Could not get AWS Account ID${NC}"
    echo "Please check your AWS credentials"
    exit 1
fi

echo -e "${GREEN}✓${NC} AWS Account ID: ${AWS_ACCOUNT_ID}"

# Construct ECR repository URL
ECR_REPO_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo ""
echo "Configuration:"
echo "  Region: ${AWS_REGION}"
echo "  Repository: ${ECR_REPO_URL}"
echo ""

# Check if local image exists
if ! docker image inspect "${IMAGE_NAME}:latest" > /dev/null 2>&1; then
    echo -e "${RED}Error: Local image ${IMAGE_NAME}:latest not found${NC}"
    echo "Please build the image first:"
    echo "  ./scripts/build-processor.sh"
    exit 1
fi

echo -e "${GREEN}✓${NC} Local image ${IMAGE_NAME}:latest found"

# Login to ECR
echo ""
echo -e "${BLUE}Logging in to ECR...${NC}"
aws ecr get-login-password --region "${AWS_REGION}" | \
    docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Successfully logged in to ECR"
else
    echo -e "${RED}Error: Failed to login to ECR${NC}"
    exit 1
fi

# Generate timestamp tag
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Tag the image
echo ""
echo -e "${BLUE}Tagging image...${NC}"
docker tag "${IMAGE_NAME}:latest" "${ECR_REPO_URL}:latest"
docker tag "${IMAGE_NAME}:latest" "${ECR_REPO_URL}:${TIMESTAMP}"

echo -e "${GREEN}✓${NC} Tagged as ${ECR_REPO_URL}:latest"
echo -e "${GREEN}✓${NC} Tagged as ${ECR_REPO_URL}:${TIMESTAMP}"

# Push to ECR
echo ""
echo -e "${BLUE}Pushing images to ECR...${NC}"
echo "This may take a few minutes..."
echo ""

# Push latest tag
echo "Pushing :latest tag..."
docker push "${ECR_REPO_URL}:latest"

# Push timestamp tag
echo ""
echo "Pushing :${TIMESTAMP} tag..."
docker push "${ECR_REPO_URL}:${TIMESTAMP}"

echo ""
echo -e "${GREEN}=====================================${NC}"
echo -e "${GREEN}✓ Push completed successfully${NC}"
echo -e "${GREEN}=====================================${NC}"
echo ""
echo "Image URIs:"
echo "  - ${ECR_REPO_URL}:latest"
echo "  - ${ECR_REPO_URL}:${TIMESTAMP}"
echo ""
echo "To use this image in ECS Task Definition:"
echo "  Image: ${ECR_REPO_URL}:latest"
echo ""
echo "To pull this image:"
echo "  docker pull ${ECR_REPO_URL}:latest"