#!/bin/bash
# Setup Subnet ID for ECS Fargate Tasks
# This script detects a public subnet in your AWS account and updates parameters/dev.json

set -e

echo "🔍 Detecting public subnet for ECS Fargate tasks..."
echo

# Get default VPC
DEFAULT_VPC=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" \
  --output text 2>/dev/null || echo "")

if [ "$DEFAULT_VPC" = "None" ] || [ -z "$DEFAULT_VPC" ]; then
  echo "⚠️  No default VPC found"
  echo
  echo "Options:"
  echo "  1. Create a default VPC: aws ec2 create-default-vpc"
  echo "  2. Use an existing VPC: Provide subnet ID manually"
  echo
  exit 1
fi

echo "✅ Found default VPC: $DEFAULT_VPC"

# Get public subnet (with internet gateway)
PUBLIC_SUBNET=$(aws ec2 describe-subnets \
  --filters \
    "Name=vpc-id,Values=$DEFAULT_VPC" \
    "Name=map-public-ip-on-launch,Values=true" \
  --query "Subnets[0].SubnetId" \
  --output text 2>/dev/null || echo "")

if [ "$PUBLIC_SUBNET" = "None" ] || [ -z "$PUBLIC_SUBNET" ]; then
  echo "⚠️  No public subnet found in default VPC"
  echo
  echo "Available subnets:"
  aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$DEFAULT_VPC" \
    --query "Subnets[*].[SubnetId,AvailabilityZone,MapPublicIpOnLaunch]" \
    --output table
  echo
  echo "Choose a subnet with MapPublicIpOnLaunch=True"
  echo "Or create one: See docs/DEPLOYMENT_GUIDE.md"
  exit 1
fi

echo "✅ Found public subnet: $PUBLIC_SUBNET"
echo

# Get subnet details
SUBNET_AZ=$(aws ec2 describe-subnets \
  --subnet-ids "$PUBLIC_SUBNET" \
  --query "Subnets[0].AvailabilityZone" \
  --output text)

SUBNET_CIDR=$(aws ec2 describe-subnets \
  --subnet-ids "$PUBLIC_SUBNET" \
  --query "Subnets[0].CidrBlock" \
  --output text)

echo "📋 Subnet Details:"
echo "   Subnet ID: $PUBLIC_SUBNET"
echo "   Availability Zone: $SUBNET_AZ"
echo "   CIDR Block: $SUBNET_CIDR"
echo "   VPC: $DEFAULT_VPC"
echo

# Ask for confirmation
read -p "Use this subnet for ECS tasks? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Cancelled. Please update SubnetId manually in infrastructure/parameters/dev.json"
  exit 0
fi

# Update parameters/dev.json
PARAMS_FILE="infrastructure/parameters/dev.json"

if [ ! -f "$PARAMS_FILE" ]; then
  echo "❌ Parameters file not found: $PARAMS_FILE"
  exit 1
fi

# Create backup
cp "$PARAMS_FILE" "${PARAMS_FILE}.backup"
echo "📦 Backup created: ${PARAMS_FILE}.backup"

# Update SubnetId using jq
if command -v jq &> /dev/null; then
  # Use jq for clean JSON manipulation
  jq --arg subnet "$PUBLIC_SUBNET" \
    'map(if .ParameterKey == "SubnetId" then .ParameterValue = $subnet else . end)' \
    "$PARAMS_FILE" > "${PARAMS_FILE}.tmp"
  mv "${PARAMS_FILE}.tmp" "$PARAMS_FILE"
  echo "✅ Updated SubnetId in $PARAMS_FILE using jq"
else
  # Fallback: use sed
  sed -i.bak "s/\"ParameterValue\": \"\"  # SubnetId/\"ParameterValue\": \"$PUBLIC_SUBNET\"/g" "$PARAMS_FILE"
  echo "✅ Updated SubnetId in $PARAMS_FILE using sed"
fi

echo
echo "✨ Setup complete!"
echo
echo "📄 Updated file: $PARAMS_FILE"
echo "🔍 Verify changes: cat $PARAMS_FILE | grep -A 1 SubnetId"
echo
echo "Next steps:"
echo "  1. Review: cat infrastructure/parameters/dev.json"
echo "  2. Deploy: sam deploy --guided --template infrastructure/template.yaml"
echo "  3. Test: Upload a video to test the pipeline"