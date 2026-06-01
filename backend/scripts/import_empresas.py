"""Import em massa de empresas a partir de CSV.

CSV esperado (UTF-8, separador `;` ou `,`):

    cnpj;razao_social;nome_fantasia;municipio;uf;regime;anexo;atividade;iss;folha_12m;cert_file;cert_password;email;fone;logradouro;numero;bairro;cep;codigo_municipio
    12345678000195;Empresa A;Empresa A Fantasia;Recife;PE;Simples Nacional;I;COMERCIO;5.00;120000;a.pfx;senha123;a@b.com;8133333333;Rua X;100;Centro;50000000;2611606
    ...

Campos obrigatorios: cnpj, razao_social, regime
Campos para Focus (opcionais — necessarios para cadastrar na Focus): cert_file, cert_password, logradouro, numero
Campos para motor de apuracao: anexo, atividade, iss, folha_12m

Modo de uso:

    docker compose exec backend python scripts/import_empresas.py \
        /data/empresas.csv \
        /data/certs

Resultado:
- Empresa cadastrada localmente.
- Se cert_file existir e USE_MOCK_FOCUS_NFE=false, cadastra na Focus e salva token.
- Logs no stdout: ✓ sucesso, ✗ erro detalhado.

Idempotente: ja existente (CNPJ duplicado) eh atualizada.
"""
from __future__ import annotations

import csv
import logging
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

# Adicionar root do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.database import SessionLocal
from app.models.empresa import Empresa
from app.schemas.integracao_schema import EmpresaFocusPayload, EnderecoFocusSchema
from app.services.empresa_integracao import EmpresaIntegracaoService
from app.utils.cnpj import normalize_cnpj, validate_cnpj


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("import_empresas")


def detectar_separador(path: Path) -> str:
    """Heuristica: se a primeira linha tem mais ';' que ',', usa ';'."""
    sample = path.read_text(encoding="utf-8").splitlines()[0]
    return ";" if sample.count(";") > sample.count(",") else ","


def upsert_empresa(db: Session, row: dict[str, str]) -> Empresa:
    """Cria ou atualiza empresa local com os campos do CSV."""
    cnpj_raw = row.get("cnpj", "").strip()
    if not validate_cnpj(cnpj_raw):
        raise ValueError(f"CNPJ invalido: {cnpj_raw}")
    cnpj = normalize_cnpj(cnpj_raw)

    emp = db.scalar(select(Empresa).where(Empresa.cnpj == cnpj))
    is_new = emp is None
    if is_new:
        emp = Empresa(cnpj=cnpj, razao_social=row["razao_social"].strip())

    # Campos basicos
    emp.razao_social = row["razao_social"].strip()
    emp.nome_fantasia = (row.get("nome_fantasia") or "").strip() or None
    emp.municipio = (row.get("municipio") or "").strip() or None
    emp.uf = (row.get("uf") or "").strip().upper() or None
    emp.regime_tributario = (row.get("regime") or "").strip() or None
    emp.anexo_simples = (row.get("anexo") or "").strip().upper() or None
    emp.atividade = (row.get("atividade") or "").strip().upper() or None

    # Campos numericos
    if row.get("iss"):
        try:
            emp.iss_aliquota = Decimal(row["iss"].replace(",", "."))
        except Exception:
            pass
    if row.get("folha_12m"):
        try:
            emp.folha_12m = Decimal(row["folha_12m"].replace(",", "."))
        except Exception:
            pass

    if is_new:
        db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


def cadastrar_focus(
    service: EmpresaIntegracaoService,
    empresa: Empresa,
    row: dict[str, str],
    certs_dir: Path,
) -> bool:
    """Sobe certificado A1 + cadastra empresa na Focus. Retorna True se OK."""
    cert_file = (row.get("cert_file") or "").strip()
    cert_pwd = (row.get("cert_password") or "").strip()
    if not cert_file or not cert_pwd:
        return False

    cert_path = certs_dir / cert_file
    if not cert_path.exists():
        log.warning("  cert nao encontrado em %s — pulando Focus", cert_path)
        return False

    payload = EmpresaFocusPayload(
        cnpj=empresa.cnpj,
        nome=empresa.razao_social,
        nome_fantasia=empresa.nome_fantasia,
        regime_tributario=empresa.regime_tributario,
        email=(row.get("email") or "").strip() or None,
        fone=(row.get("fone") or "").strip() or None,
        endereco=EnderecoFocusSchema(
            logradouro=(row.get("logradouro") or "Rua").strip(),
            numero=(row.get("numero") or "S/N").strip(),
            bairro=(row.get("bairro") or "").strip() or None,
            cep=(row.get("cep") or "").strip() or None,
            codigo_municipio=(row.get("codigo_municipio") or "").strip() or None,
            cidade=empresa.municipio,
            uf=empresa.uf,
        ),
    )
    try:
        service.sync_empresa(
            empresa.id, payload,
            certificado_bytes=cert_path.read_bytes(),
            certificado_filename=cert_file,
            certificado_password=cert_pwd,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("  Focus falhou para %s: %s", empresa.razao_social, exc)
        return False


def main(csv_path: str, certs_dir: str) -> None:
    settings = get_settings()
    log.info("USE_MOCK_FOCUS_NFE=%s · USE_MOCK_INTEGRA=%s",
             settings.use_mock_focus_nfe, settings.use_mock_integra)

    csv_path_p = Path(csv_path)
    certs_dir_p = Path(certs_dir)
    if not csv_path_p.exists():
        log.error("CSV nao encontrado: %s", csv_path_p)
        sys.exit(1)
    if not certs_dir_p.exists():
        log.warning("Diretorio de certs nao existe: %s — empresas nao serao cadastradas na Focus", certs_dir_p)

    sep = detectar_separador(csv_path_p)
    log.info("Separador detectado: '%s'", sep)

    db = SessionLocal()
    service = EmpresaIntegracaoService(db)
    sucesso = 0
    falha = 0
    focus_ok = 0
    try:
        with open(csv_path_p, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=sep)
            for i, row in enumerate(reader, start=1):
                cnpj = row.get("cnpj", "").strip()
                razao = row.get("razao_social", "").strip()
                try:
                    emp = upsert_empresa(db, row)
                    log.info("[%d] ✓ %s (id=%d) %s", i, razao, emp.id, cnpj)
                    sucesso += 1
                    if certs_dir_p.exists() and not settings.use_mock_focus_nfe:
                        if cadastrar_focus(service, emp, row, certs_dir_p):
                            focus_ok += 1
                            log.info("    └─ Focus OK · token salvo")
                except Exception as exc:  # noqa: BLE001
                    falha += 1
                    log.error("[%d] ✗ %s: %s", i, razao or cnpj, exc)
    finally:
        db.close()

    log.info("=" * 60)
    log.info("FIM. Sucesso: %d · Falhas: %d · Focus cadastradas: %d", sucesso, falha, focus_ok)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
