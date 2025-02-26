#!/bin/bash
# Script to help debug Docker build memory issues

# Set the image name
IMAGE_NAME="texting-concierge-agent"

# Clean up any existing containers and images
echo "Cleaning up existing containers and images..."
docker ps -a | grep $IMAGE_NAME | awk '{print $1}' | xargs -r docker rm -f
docker images | grep $IMAGE_NAME | awk '{print $3}' | xargs -r docker rmi -f

# Build with verbose output and increased memory limit
echo "Building Docker image with increased memory limit..."
docker build \
  --memory=4g \
  --memory-swap=4g \
  --progress=plain \
  -t $IMAGE_NAME \
  .

# Check build status
if [ $? -eq 0 ]; then
  echo "Build successful!"
  echo "Testing the container..."
  
  # Run the container with limited resources to simulate Railway environment
  docker run \
    --name $IMAGE_NAME-test \
    --memory=512m \
    --memory-swap=512m \
    --cpus=0.5 \
    -p 8080:8080 \
    -p 8443:8443 \
    -d \
    $IMAGE_NAME
  
  # Wait for container to start
  echo "Waiting for container to start..."
  sleep 5
  
  # Check if container is running
  if docker ps | grep $IMAGE_NAME-test > /dev/null; then
    echo "Container is running!"
    echo "Testing health check endpoint..."
    
    # Test health check endpoint
    curl -v http://localhost:8080/telegram/webhook
    
    echo "Container logs:"
    docker logs $IMAGE_NAME-test
  else
    echo "Container failed to start!"
    docker logs $IMAGE_NAME-test
  fi
  
  # Clean up test container
  echo "Cleaning up test container..."
  docker rm -f $IMAGE_NAME-test
else
  echo "Build failed!"
fi 