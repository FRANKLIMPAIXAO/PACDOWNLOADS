#!/usr/bin/env bash
# =============================================================
# Setup inicial do PAC Download numa VPS Ubuntu 22.04 LTS limpa.
# Rodar como root: bash deploy/deploy.sh
# =============================================================

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/pac-xml-downloader}"
DOMINIO_APP="${DOMINIO_APP:-app.SEUDOMINIO.com.br}"
DOMINIO_API="${DOMINIO_API:-api.SEUDOMINIO.com.br}"
EMAIL_LE="${EMAIL_LE:-seu@email.com}"

log() { echo -e "\n\033[1;32m[deploy]\033[0m $*"; }
err() { echo -e "\n\033[1;31m[erro]\033[0m $*"; exit 1; }

# 1. Sistema
log "Atualizando sistema..."
apt update && apt upgrade -y
apt install -y curl git ufw fail2ban

# 2. Docker
if ! command -v docker &>/dev/null; then
  log "Instalando Docker..."
  curl -fsSL https://get.docker.com | sh
fi

# 3. Firewall
log "Configurando firewall..."
ufw --force enable
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw status verbose

# 4. Repositório
if [[ ! -d "$REPO_DIR" ]]; then
  err "Repositório não encontrado em $REPO_DIR. Clone primeiro."
fi
cd "$REPO_DIR"

# 5. .env
if [[ ! -f backend/.env ]]; then
  log "Criando backend/.env a partir do template..."
  cp backend/.env.production.example backend/.env
  echo
  echo "=================================================="
  echo "EDITE backend/.env AGORA com:"
  echo "  - SECRET_KEY (gerar com: openssl rand -hex 32)"
  echo "  - POSTGRES_PASSWORD"
  echo "  - FOCUS_MASTER_TOKEN"
  echo "  - SERPRO_CONSUMER_KEY / SERPRO_CONSUMER_SECRET"
  echo "  - SERPRO_CERT_PATH (suba o .pfx para backend/certs/)"
  echo "  - SERPRO_CERT_PASSWORD"
  echo "  - SERPRO_CONTRATANTE_CNPJ / SERPRO_AUTOR_PEDIDO_CNPJ"
  echo "  - CAPTCHA_API_KEY"
  echo "  - PUBLIC_API_URL=https://$DOMINIO_API"
  echo "=================================================="
  read -p "Pressione ENTER após editar o .env..."
fi

# 6. Substituir SEUDOMINIO no nginx.conf
sed -i "s/SEUDOMINIO.com.br/$DOMINIO_APP $DOMINIO_API/g" deploy/nginx.conf
log "deploy/nginx.conf atualizado com seus domínios"

# 7. Subir stack (HTTP-only inicialmente para o certbot)
log "Construindo imagens..."
docker compose -f docker-compose.production.yml build

log "Subindo containers..."
docker compose -f docker-compose.production.yml up -d

# 8. Aguardar backend ficar pronto
log "Aguardando backend ficar pronto..."
for i in {1..30}; do
  if docker compose exec -T backend curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    log "Backend OK"
    break
  fi
  sleep 5
done

# 9. Aplicar migrations
log "Aplicando migrations..."
docker compose -f docker-compose.production.yml exec backend python -m alembic upgrade head

# 10. Gerar certificado SSL
log "Gerando certificado Let's Encrypt..."
docker compose -f docker-compose.production.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  -d "$DOMINIO_APP" -d "$DOMINIO_API" \
  --email "$EMAIL_LE" --agree-tos --no-eff-email --non-interactive

# 11. Habilitar HTTPS no nginx (descomenta os blocos 443)
log "Habilitando HTTPS no nginx.conf..."
sed -i 's/^# server {/server {/' deploy/nginx.conf
sed -i 's/^#     /    /' deploy/nginx.conf
sed -i 's/^# }/}/' deploy/nginx.conf
# Ativa redirect HTTP → HTTPS
sed -i '/# location \/ {/,/# }/{
  s/# //
}' deploy/nginx.conf

docker compose -f docker-compose.production.yml restart nginx

log "✅ Deploy concluído!"
echo
echo "Acesse:"
echo "  Frontend: https://$DOMINIO_APP"
echo "  API:      https://$DOMINIO_API"
echo "  Health:   https://$DOMINIO_API/health"
echo
echo "Login default: admin@SEUDOMINIO.com.br / TROCAR_NA_PRIMEIRA_LOGIN"
echo
echo "Próximos passos:"
echo "  1. Logue no frontend e troque a senha do admin"
echo "  2. Cadastre 1 empresa de teste (homologação)"
echo "  3. Configure backup com: bash deploy/backup.sh"
echo "  4. Adicione no crontab: 0 3 * * * cd $REPO_DIR && bash deploy/backup.sh"
