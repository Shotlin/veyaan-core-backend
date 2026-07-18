#!/bin/bash
# VEYAAN Core Backend - Server Bootstrap Script
# Run on fresh Ubuntu ARM64 server

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   log_error "This script should not be run as root. Run as a non-root user with sudo privileges."
   exit 1
fi

# Update system
log_info "Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# Create non-root admin user if not exists
ADMIN_USER="veyaan"
if ! id "$ADMIN_USER" &>/dev/null; then
    log_info "Creating admin user: $ADMIN_USER"
    sudo adduser --disabled-password --gecos "" $ADMIN_USER
    sudo usermod -aG sudo $ADMIN_USER
    sudo usermod -aG docker $ADMIN_USER 2>/dev/null || true
else
    log_info "Admin user $ADMIN_USER already exists"
fi

# SSH key authentication
log_info "Configuring SSH..."
sudo mkdir -p /home/$ADMIN_USER/.ssh
sudo chmod 700 /home/$ADMIN_USER/.ssh
# Add your public key here or use ssh-copy-id from your machine
# sudo cat >> /home/$ADMIN_USER/.ssh/authorized_keys << 'EOF'
# ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... your-key-here
# EOF
sudo chmod 600 /home/$ADMIN_USER/.ssh/authorized_keys 2>/dev/null || true
sudo chown -R $ADMIN_USER:$ADMIN_USER /home/$ADMIN_USER/.ssh

# Disable password auth for SSH
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl reload sshd

# Firewall
log_info "Configuring firewall..."
sudo ufw allow 22/tcp comment 'SSH'
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'
sudo ufw --force enable

# Install Docker
log_info "Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $ADMIN_USER
else
    log_info "Docker already installed"
fi

# Install Docker Compose
log_info "Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo apt-get install -y docker-compose-plugin
else
    log_info "Docker Compose already installed"
fi

# Install Tailscale
log_info "Installing Tailscale..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
else
    log_info "Tailscale already installed"
fi

# Create application directory
APP_DIR="/opt/veyaan"
log_info "Creating application directory: $APP_DIR"
sudo mkdir -p $APP_DIR
sudo chown $ADMIN_USER:$ADMIN_USER $APP_DIR

# Set up log rotation
log_info "Configuring log rotation..."
sudo tee /etc/logrotate.d/veyaan > /dev/null <<'EOF'
/opt/veyaan/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0640 veyaan veyaan
}
EOF

# Time synchronization
log_info "Configuring time synchronization..."
sudo timedatectl set-timezone UTC
sudo systemctl enable systemd-timesyncd
sudo systemctl start systemd-timesyncd

# Create .env directory with restricted permissions
log_info "Creating environment directory..."
mkdir -p $APP_DIR/env
chmod 700 $APP_DIR/env

log_info "Bootstrap complete!"
log_info "Next steps:"
log_info "1. Copy your SSH public key to /home/$ADMIN_USER/.ssh/authorized_keys"
log_info "2. Clone the repository to $APP_DIR"
log_info "3. Create .env file in $APP_DIR/env/ with production values"
log_info "4. Run: docker compose -f $APP_DIR/docker-compose.yml up -d"
log_info "5. Run: tailscale up"