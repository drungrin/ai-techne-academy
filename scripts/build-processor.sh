#!/bin/bash
# AI Techne Academy - Build Processor Docker Image
# This script builds the processor container image locally

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
IMAGE_NAME="ai-techne-processor"
IMAGE_TAG="${1:-latest}"
BUILD_DIR="src/processor"

echo -e "${YELLOW}=====================================${NC}"
echo -e "${YELLOW}AI Techne Academy - Processor Build${NC}"
echo -e "${YELLOW}=====================================${NC}"
echo ""

# Check if we're in the project root
if [ ! -d "$BUILD_DIR" ]; then
    echo -e "${RED}Error: Must run from project root directory${NC}"
    echo -e "${RED}Expected to find: $BUILD_DIR${NC}"
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}"
    echo "Please start Docker and try again"
    exit 1
fi

echo -e "${GREEN}✓${NC} Docker is running"
echo ""

# Build the image
echo -e "${YELLOW}Building Docker image...${NC}"
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo "Context: ${BUILD_DIR}"
echo ""

cd "$BUILD_DIR"

docker build \
    --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
    --tag "${IMAGE_NAME}:latest" \
    --build-arg BUILDKIT_INLINE_CACHE=1 \
    .

BUILD_STATUS=$?
cd - > /dev/null

if [ $BUILD_STATUS -eq 0 ]; then
    echo ""
    echo -e "${GREEN}=====================================${NC}"
    echo -e "${GREEN}✓ Build completed successfully${NC}"
    echo -e "${GREEN}=====================================${NC}"
    echo ""
    echo "Image tags:"
    echo "  - ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "  - ${IMAGE_NAME}:latest"
    echo ""
    echo "To run the container:"
    echo "  docker run --rm -it ${IMAGE_NAME}:latest python main.py --help"
    echo ""
    echo "To test with docker-compose:"
    echo "  cd src/processor && docker-compose up -d"
else
    echo ""
    echo -e "${RED}=====================================${NC}"
    echo -e "${RED}✗ Build failed${NC}"
    echo -e "${RED}=====================================${NC}"
    exit 1
fi