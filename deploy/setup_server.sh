#!/bin/bash
# Script de deploiement ClimaSen sur VPS Hostinger
# Lancer en tant que root : bash setup_server.sh

set -e

APP_USER="climatsen"
APP_DIR="/home/$APP_USER/app"
REPO_URL="https://github.com/laityfaye/ClimaSen.git"
DOMAIN="climatsen.innosft.com"

echo "=== [1/8] Mise a jour du systeme ==="
apt-get update -y && apt-get upgrade -y

echo "=== [2/8] Installation des dependances systeme ==="
apt-get install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx \
    libhdf5-dev libnetcdf-dev curl

echo "=== [3/8] Creation de l'utilisateur applicatif ==="
id -u $APP_USER &>/dev/null || useradd -m -s /bin/bash $APP_USER

echo "=== [4/8] Clone du depot Git ==="
su - $APP_USER -c "
    rm -rf $APP_DIR
    git clone $REPO_URL $APP_DIR
"

echo "=== [5/8] Creation du virtualenv et installation des packages ==="
su - $APP_USER -c "
    cd $APP_DIR
    python3 -m venv venv
    venv/bin/pip install --upgrade pip
    venv/bin/pip install -r requirements.txt
"

echo "=== [6/8] Creation des dossiers de donnees ==="
su - $APP_USER -c "
    mkdir -p $APP_DIR/data/raw/SST
    mkdir -p $APP_DIR/data/raw/climate_indices
    mkdir -p $APP_DIR/data/processed
    mkdir -p $APP_DIR/outputs/teleconnections/visualizations
    mkdir -p $APP_DIR/outputs/visualizations
    mkdir -p $APP_DIR/outputs/exports
    mkdir -p $APP_DIR/outputs/clustering
"

echo "=== [7/8] Installation du service systemd ==="
cp $APP_DIR/deploy/climatsen.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable climatsen
systemctl start climatsen

echo "=== [8/8] Configuration Nginx ==="
cp $APP_DIR/deploy/nginx-climatsen.conf /etc/nginx/sites-available/climatsen
ln -sf /etc/nginx/sites-available/climatsen /etc/nginx/sites-enabled/climatsen
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "=== INSTALLATION TERMINEE ==="
echo "Prochaine etape : configurer le DNS puis lancer :"
echo "  certbot --nginx -d $DOMAIN"
echo ""
echo "Status de l'app :"
systemctl status climatsen --no-pager
