#!/bin/sh
# Entrypoint do backend PAC.
#
# Roda `alembic upgrade head` ANTES de iniciar o processo principal, garantindo
# que o schema do banco esteja sempre na versao mais recente apos cada deploy.
#
# Sem isso, migrations novas (ex: 0019 que aumenta situacoes_fiscais.protocolo
# de VARCHAR(80) para VARCHAR(500)) nunca rodam em prod, e o codigo novo crasha
# ao tentar salvar dados que nao cabem no schema antigo (StringDataRightTruncation).
#
# main.py faz `Base.metadata.create_all` que SO cria tabelas faltantes — NAO
# altera colunas existentes. Por isso alembic e obrigatorio.
#
# Resiliente: se a migration falhar, loga e continua (app sobe mesmo assim, pra
# nao deixar o servico fora do ar por um problema de migration).

set -e
cd /app

echo "[entrypoint] Rodando alembic upgrade head..."
if alembic upgrade head; then
    echo "[entrypoint] Migrations aplicadas com sucesso."
else
    echo "[entrypoint] AVISO: alembic upgrade falhou. Iniciando app mesmo assim."
fi

echo "[entrypoint] Iniciando processo principal: $*"
exec "$@"
