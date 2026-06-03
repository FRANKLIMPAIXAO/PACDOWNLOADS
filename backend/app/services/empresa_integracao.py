from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.empresa import Empresa
from app.providers.focus_nfe import (
    FocusEmpresaNaoCadastradaError,
    FocusNFeProvider,
)
from app.schemas.integracao_schema import (
    EmpresaFocusPayload,
    StatusIntegracaoEmpresaRead,
)


settings = get_settings()


class EmpresaIntegracaoService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = FocusNFeProvider()

    def get_empresa_or_404(self, empresa_id: int) -> Empresa:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa nao encontrada")
        return empresa

    def sync_empresa(
        self,
        empresa_id: int,
        payload: EmpresaFocusPayload,
        certificado_bytes: bytes,
        certificado_filename: str,
        certificado_password: str,
        *,
        dry_run: bool = False,
    ) -> dict:
        """Cadastra ou atualiza a empresa na Focus NFe e persiste o token retornado.

        Para o cadastro inicial usa o `FOCUS_MASTER_TOKEN` (token-mestre da conta).
        Para a atualizacao, usa o token da propria empresa ja salvo localmente.
        """
        empresa = self.get_empresa_or_404(empresa_id)
        empresa.cnpj = payload.cnpj
        empresa.razao_social = payload.nome
        empresa.nome_fantasia = payload.nome_fantasia
        empresa.municipio = payload.endereco.cidade
        empresa.uf = payload.endereco.uf
        if payload.regime_tributario:
            empresa.regime_tributario = payload.regime_tributario
        self.db.commit()

        token_atual = empresa.get_focus_token()
        if token_atual:
            data = self.provider.atualizar_empresa(
                token_atual,
                empresa.cnpj,
                payload=payload.model_dump(exclude={"endereco"}) | payload.endereco.model_dump(),
                certificado_bytes=certificado_bytes,
                certificado_filename=certificado_filename,
                certificado_password=certificado_password,
            )
        else:
            if not settings.focus_master_token and not settings.use_mock_focus_nfe:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "FOCUS_MASTER_TOKEN nao configurado. Cadastre a empresa "
                        "manualmente no painel Focus e use PUT /empresas/{id}/focus/token."
                    ),
                )
            data = self.provider.cadastrar_empresa(
                settings.focus_master_token,
                payload=payload.model_dump(exclude={"endereco"}) | payload.endereco.model_dump(),
                certificado_bytes=certificado_bytes,
                certificado_filename=certificado_filename,
                certificado_password=certificado_password,
                dry_run=dry_run,
            )
            # Em dry_run a Focus retorna {"status":"validacao_ok"} sem token —
            # nada pra persistir.
            if not dry_run:
                token = data.get("token_producao") or data.get("token_homologacao")
                if token:
                    empresa.set_focus_token(str(token))
                    self.db.commit()
        return self._scrub_tokens(data) or {}

    def importar_token(self, empresa_id: int, token: str) -> Empresa:
        """Salva localmente um token Focus gerado fora do sistema (painel Focus)."""
        empresa = self.get_empresa_or_404(empresa_id)
        empresa.set_focus_token(token)
        self.db.commit()
        self.db.refresh(empresa)
        return empresa

    def status_integracao(self, empresa_id: int) -> StatusIntegracaoEmpresaRead:
        """Status da empresa no painel Focus.

        IMPORTANTE: o endpoint /v2/empresas/{cnpj} so aceita o TOKEN MESTRE da
        conta (admin/full account access) — tokens de empresa retornam 401.
        Usamos o master token do .env quando disponivel; quando nao disponivel,
        cai pra retorno vazio (sem expor erro 500 ao cliente).
        """
        from app.config import get_settings as _gs
        _s = _gs()
        empresa = self.get_empresa_or_404(empresa_id)
        empresa_focus: dict | None = None
        master = (_s.focus_master_token or "").strip()
        if master:
            try:
                empresa_focus = self.provider.consultar_empresa(master, empresa.cnpj)
                empresa_focus = self._scrub_tokens(empresa_focus)
            except FocusEmpresaNaoCadastradaError:
                empresa_focus = None
            except Exception:
                # Qualquer outra falha (rede, 401, etc) nao deve derrubar a tela.
                empresa_focus = None
        return StatusIntegracaoEmpresaRead(
            empresa_local_id=empresa.id,
            empresa_local_cnpj=empresa.cnpj,
            tem_token=empresa.has_focus_token,
            empresa_focus=empresa_focus,
        )

    @staticmethod
    def _scrub_tokens(data: dict | None) -> dict | None:
        """Remove qualquer campo de token antes de devolver dados ao cliente."""
        if not isinstance(data, dict):
            return data
        return {
            k: v for k, v in data.items()
            if k not in {"token_producao", "token_homologacao"}
        }
