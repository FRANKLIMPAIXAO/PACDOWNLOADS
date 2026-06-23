"""Solicitação de admissão (portal do cliente) + entrega ao PAC TAREFAS (webhook).

Segurança/LGPD: dado pessoal sensível (CPF, dependentes). Escopo SEMPRE pela
empresa do TOKEN do cliente. Anexos guardados em disco; o webhook leva só os
LINKS (PAC TAREFAS baixa com a X-API-Key) — não trafega base64 gigante."""
from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.empresa import Empresa
from app.models.solicitacao_admissao import SolicitacaoAdmissao

logger = logging.getLogger("pac.admissao")

_MAX_ANEXO = 25 * 1024 * 1024  # 25 MB por anexo


def _so_digitos(v: str | None) -> str | None:
    return re.sub(r"\D", "", v) if v else None


class AdmissaoService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()

    def criar(
        self, empresa: Empresa, criado_por_id: int | None,
        dados: dict, anexos_in: list[dict] | None,
    ) -> SolicitacaoAdmissao:
        """Cria a solicitação: salva anexos no disco e grava a linha. NÃO envia o
        webhook ainda (quem chama decide enviar — pra responder rápido ao cliente)."""
        sol = SolicitacaoAdmissao(
            empresa_id=empresa.id,
            criado_por_id=criado_por_id,
            status="nova",
            funcionario_nome=(dados.get("nome") or dados.get("funcionario_nome") or "")[:160] or None,
            funcionario_cpf=(_so_digitos(dados.get("cpf")) or None),
            cargo=(dados.get("funcao") or dados.get("cargo") or "")[:120] or None,
            dados=json.dumps(dados, ensure_ascii=False),
        )
        # data de admissão (ISO AAAA-MM-DD) se válida
        da = dados.get("data_admissao")
        if da:
            try:
                sol.data_admissao = datetime.strptime(da[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
        self.db.add(sol)
        self.db.flush()  # pega o id pra nomear a pasta dos anexos

        anexos_meta: list[dict] = []
        if anexos_in:
            pasta = Path(self.settings.storage_path) / "admissoes" / empresa.cnpj / str(sol.id)
            pasta.mkdir(parents=True, exist_ok=True)
            for i, a in enumerate(anexos_in[:20]):  # teto de 20 anexos
                b64 = a.get("base64") or ""
                if not b64:
                    continue
                try:
                    raw = base64.b64decode(b64, validate=True)
                except Exception:  # noqa: BLE001
                    continue
                if not raw or len(raw) > _MAX_ANEXO:
                    continue
                nome = re.sub(r"[^A-Za-z0-9._-]", "_", (a.get("nome") or f"anexo_{i}.bin"))[:120]
                caminho = pasta / f"{i}_{nome}"
                caminho.write_bytes(raw)
                anexos_meta.append({"nome": nome, "path": str(caminho)})
        sol.anexos = json.dumps(anexos_meta, ensure_ascii=False)
        self.db.commit()
        self.db.refresh(sol)
        return sol

    def enviar_webhook(self, sol: SolicitacaoAdmissao, empresa: Empresa) -> bool:
        """Empurra a solicitação pro PAC TAREFAS. Resiliente: marca sucesso/erro na
        própria linha; nunca levanta (o cliente já teve a solicitação salva)."""
        url = self.settings.pac_tarefas_webhook_url
        if not url:
            sol.envio_erro = "Webhook do PAC TAREFAS não configurado (PAC_TAREFAS_WEBHOOK_URL)."
            self.db.commit()
            return False
        try:
            anexos = json.loads(sol.anexos) if sol.anexos else []
        except Exception:  # noqa: BLE001
            anexos = []
        base = self.settings.api_public_url.rstrip("/")
        payload = {
            "id": sol.id,
            "tipo": "solicitacao_admissao",
            "empresa": {"id": empresa.id, "cnpj": empresa.cnpj, "razao_social": empresa.razao_social},
            "criado_em": sol.criado_em.isoformat() if sol.criado_em else None,
            "dados": json.loads(sol.dados) if sol.dados else {},
            "anexos": [
                {"indice": i, "nome": a.get("nome"),
                 "url": f"{base}/api/v1/integracao/admissoes/{sol.id}/anexo/{i}"}
                for i, a in enumerate(anexos)
            ],
        }
        headers = {"X-PAC-Token": self.settings.pac_tarefas_webhook_token} if self.settings.pac_tarefas_webhook_token else {}
        try:
            r = httpx.post(url, json=payload, headers=headers, timeout=20)
            r.raise_for_status()
            sol.enviado_pactarefas = True
            sol.enviado_em = datetime.now(timezone.utc)
            sol.envio_erro = None
            self.db.commit()
            logger.info("admissao %s enviada ao PAC TAREFAS (empresa %s)", sol.id, empresa.id)
            return True
        except Exception as exc:  # noqa: BLE001
            sol.enviado_pactarefas = False
            sol.envio_erro = str(exc)[:380]
            self.db.commit()
            logger.warning("Falha ao enviar admissao %s ao PAC TAREFAS: %s", sol.id, exc)
            return False
