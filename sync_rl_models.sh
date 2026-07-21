#!/bin/bash
# Sync RL models from pc-casa to all servers

set -e

MODEL_DIR="rylos_rl_v1_gpu"
PC_CASA="marco@home.ziliani.net"
PC_CASA_PORT="22222"
DEBIAN="marco@192.168.0.34"
AWS="admin@amazon.ziliani.net"

echo "==================================="
echo "RyLoS RL Model Sync Script"
echo "==================================="
echo ""

# 1. Sync from pc-casa to pc-work
echo "📥 [1/3] Syncing models from pc-casa to pc-work..."
rsync -avz --progress -e "ssh -p ${PC_CASA_PORT}" \
  ${PC_CASA}:/home/marco/dev/freqtrade/user_data/models/${MODEL_DIR}/ \
  user_data/models/${MODEL_DIR}/

echo ""
echo "✅ Sync from pc-casa completed!"
echo ""

# 2. Sync from pc-work to debian
echo "📤 [2/3] Syncing models from pc-work to debian..."
rsync -avz --progress \
  user_data/models/${MODEL_DIR}/ \
  ${DEBIAN}:/opt/freqtrade/user_data/models/${MODEL_DIR}/

echo ""
echo "✅ Sync to debian completed!"
echo ""

# 3. Sync from pc-work to AWS
echo "📤 [3/3] Syncing models from pc-work to AWS..."
rsync -avz --progress \
  user_data/models/${MODEL_DIR}/ \
  ${AWS}:/opt/freqtrade/user_data/models/${MODEL_DIR}/

echo ""
echo "✅ Sync to AWS completed!"
echo ""

# Summary
echo "==================================="
echo "✅ All models synced successfully!"
echo "==================================="
echo ""
echo "Model directory: user_data/models/${MODEL_DIR}/"
echo ""
echo "Synced to:"
echo "  - pc-work (local)"
echo "  - debian (${DEBIAN})"
echo "  - AWS (${AWS})"
echo ""
echo "You can now use the trained models on all servers!"
