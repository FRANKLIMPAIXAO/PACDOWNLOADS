"""Servico de emissao/renovacao automatica de comprovantes de regularidade fiscal.

Roteamento por tipo:
- FEDERAL          -> SITFIS via Integra Contador (Serpro). Sem captcha,
                      sem Playwright. Validade pratica: 60 dias.
- FEDERAL_OFICIAL  -> CND Conjunta RFB+PGFN no portal Receita Federal,
                      via Playwright + 2captcha. Necessaria para licitacoes,
                      bancos e contratos publicos. Validade: 180 dias.
- TRABALHISTA      -> CNDT no portal TST via Playwright + 2captcha. 180d.
- FGTS             -> CRF Caixa Economica via Playwright + 2captcha. 30d.
- ESTADUAL         -> Cadastro manual (varia por SEFAZ). Sem robo.
- MUNICIPAL        -> Cadastro manual (varia por prefeitura). Sem robo.

Fluxo `renovar_cnd(empresa_id, tipo)`:
1. Roteia para o servico correto (Integra ou Sefaz).
2. Salva PDF em `storage/cnds/<cnpj>/<tipo>_<YYYYMMDD>_<numero>.pdf`.
3. Cria nova `Certidao` com data_emissao + data_validade vindas da fonte.
4. Retorna a Certidao recem-criada.

Fluxo `renovar_vencendo(janela_dias=7)`:
- Para cada empresa ativa com comprovante vencendo em <= janela_dias (ou ja
  vencido), emite novo automaticamente. Retorna estatisticas.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.certidao import Certidao, TipoCertidao
from app.models.empresa import Empresa
from app.providers.infosimples import (
    CndInfosimples,
    InfosimplesError,
    InfosimplesProdutoNaoHabilitado,
    InfosimplesSaldoInsuficiente,
)
from app.providers.sefaz_robot import (
    CndEmitida,
    SefazRobotError,
    SefazRobotProvider,
    TipoCnd,
    VALIDADES_DIAS,
)
from app.services.infosimples_service import InfosimplesService
from app.services.integra_contador_service import IntegraContadorService


logger = logging.getLogger(__name__)
_settings = get_settings()


def _analisar_sitfis_pdf(pdf_path: str | None) -> tuple[bool | None, list[str]]:
    """Lê o PDF do SITFIS e detecta pendências no 'Diagnóstico Fiscal'.

    Retorna (regular, pendencias):
      - regular=True  → sem pendências (situação regular / apta a negativa);
      - regular=False → há pendências (omissão de DEFIS/DCTFWeb, débito, etc.);
      - regular=None  → não deu pra avaliar (PDF ilegível ou formato diferente) —
        o portal trata como "verificar", NUNCA como válida.

    Conservador de propósito: na dúvida devolve None (não afirma regularidade).
    """
    if not pdf_path:
        return None, []
    try:
        import pdfplumber
    except Exception:  # noqa: BLE001
        logger.warning("pdfplumber indisponível — SITFIS não analisado")
        return None, []
    try:
        partes: list[str] = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                partes.append(page.extract_text() or "")
        texto = "\n".join(partes)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao ler SITFIS %s: %s", pdf_path, exc)
        return None, []

    if not texto.strip() or "diagn" not in texto.lower():
        # Sem texto extraível ou sem a seção de Diagnóstico → não dá pra afirmar.
        return None, []

    pendencias: list[str] = []
    vistos: set[str] = set()
    for raw in texto.splitlines():
        linha = raw.strip()
        if not linha or not linha.lower().startswith("pend"):  # "Pendência - ..."
            continue
        item = linha.split("-", 1)[1].strip() if "-" in linha else linha
        item = item.strip("*•– ").strip()
        if item and item.lower() not in {"pendência", "pendencia"} and item not in vistos:
            vistos.add(item)
            pendencias.append(item[:160])

    if pendencias:
        return False, pendencias[:20]
    # Diagnóstico presente e nenhuma linha "Pendência -" → regular.
    return True, []


# Tipos onde renovacao automatica esta disponivel (cards do CndCard)
TIPOS_AUTOMATIZAVEIS: tuple[str, ...] = (
    "FEDERAL", "FEDERAL_OFICIAL", "TRABALHISTA", "FGTS",
)


@dataclass(slots=True)
class RenovacaoResultado:
    sucesso: int = 0
    falhas: int = 0
    pulados: int = 0
    detalhes: list[dict] | None = None

    def __post_init__(self):
        if self.detalhes is None:
            self.detalhes = []


class CndRoboService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = SefazRobotProvider()  # fallback legacy (não usado hoje)
        self.integra_service = IntegraContadorService(db)
        self.infosimples = InfosimplesService(db)

    # --- Roteamento principal ---

    def renovar_cnd(
        self, empresa_id: int, tipo: TipoCnd, *, force: bool = False,
    ) -> Certidao:
        """Renova um comprovante.

        Roteamento (custo decrescente):
        - FEDERAL / FEDERAL_OFICIAL -> Integra Contador (Serpro) via SITFIS.
          ~R$ 0,03/consulta. CND Conjunta RFB+PGFN extraída do mesmo SITFIS.
        - FGTS / ESTADUAL -> Infosimples (~R$ 0,20/consulta).
          Substitui o velho SefazRobotProvider (Playwright + 2captcha).
        - TRABALHISTA -> manual. Consultas raras (só licitação/banco),
          não compensa custo recorrente de Infosimples.
        - MUNICIPAL -> manual.

        `force=True` bypassa cache do Infosimples (usuário clicou "atualizar").
        """
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa nao encontrada",
            )

        if tipo in ("FEDERAL", "FEDERAL_OFICIAL"):
            return self._renovar_federal_via_sitfis(empresa, tipo_alvo=tipo)
        if tipo in ("FGTS", "ESTADUAL"):
            return self._renovar_via_infosimples(empresa, tipo, force=force)
        # TRABALHISTA / MUNICIPAL não têm provider — caller deve cadastrar manual
        raise HTTPException(
            status_code=400,
            detail=(
                f"Tipo {tipo} não tem renovação automática. "
                "Emita a certidão no portal oficial e cadastre via POST /cnds/empresa/{id}."
            ),
        )

    # --- FEDERAL / FEDERAL_OFICIAL via SITFIS (Integra Contador) ---

    def _renovar_federal_via_sitfis(
        self, empresa: Empresa, *, tipo_alvo: TipoCnd = "FEDERAL",
    ) -> Certidao:
        """Gera SITFIS via Integra Contador e cria registro de Certidao.

        Aproveita o `IntegraContadorService.gerar_situacao_fiscal` ja existente,
        que faz SOLICITARPROTOCOLO91 + RELATORIOSITFIS92 (com retry/wait), salva
        PDF em `storage/sitfis/{cnpj}/{ts}.pdf` e cria registro em
        `situacoes_fiscais`. Aqui criamos UMA Certidao apontando para esse PDF.

        Args:
            tipo_alvo: 'FEDERAL' (uso interno, validade 60d) ou 'FEDERAL_OFICIAL'
                (CND Conjunta RFB+PGFN, validade 180d). O dado é o mesmo (SITFIS
                contém todas as informações da CND Conjunta), só muda a validade
                legal e a observação registrada.
        """
        try:
            situacao = self.integra_service.gerar_situacao_fiscal(empresa.id)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("SITFIS falhou para %s", empresa.cnpj)
            raise HTTPException(status_code=502, detail=f"SITFIS falhou: {exc}") from exc

        if not situacao.pdf_path:
            raise HTTPException(
                status_code=502, detail="SITFIS retornou sem PDF.",
            )

        hoje = date.today()
        validade = hoje + timedelta(days=VALIDADES_DIAS[tipo_alvo])

        # Lê o Diagnóstico Fiscal do SITFIS pra saber se há pendências. Esse
        # marcador (SITUACAO_FISCAL=...) é o que o portal usa pra NÃO mostrar
        # "Válida" pra empresa irregular. SITFIS ≠ certidão negativa.
        regular, pendencias = _analisar_sitfis_pdf(situacao.pdf_path)
        sit_tag = "REGULAR" if regular is True else ("COM_PENDENCIAS" if regular is False else "DESCONHECIDA")
        marcador = f"SITUACAO_FISCAL={sit_tag}. "
        if pendencias:
            marcador += "Pendências: " + "; ".join(pendencias) + ". "

        if tipo_alvo == "FEDERAL_OFICIAL":
            obs = marcador + (
                "Extraido do SITFIS via Integra Contador. "
                f"Protocolo: {situacao.protocolo}. Validade 180d."
            )
        else:
            obs = marcador + (
                "Relatorio SITFIS via Integra Contador (uso interno). "
                f"Protocolo: {situacao.protocolo}. Validade 60d."
            )

        cert = Certidao(
            empresa_id=empresa.id,
            tipo=TipoCertidao(tipo_alvo),
            numero=f"SITFIS-{situacao.id}",
            data_emissao=hoje,
            data_validade=validade,
            pdf_path=situacao.pdf_path,  # reutiliza PDF do SITFIS
            observacoes=obs,
        )
        self.db.add(cert)
        self.db.commit()
        self.db.refresh(cert)
        return cert

    # --- FGTS / TRABALHISTA / FEDERAL_OFICIAL / ESTADUAL via Infosimples ---

    def _renovar_via_infosimples(
        self, empresa: Empresa, tipo: TipoCnd, *, force: bool = False,
    ) -> Certidao:
        """Consulta CND via Infosimples (com cache TTL automático).

        Mapeia erros do provider em HTTPException compreensíveis:
        - Produto não habilitado → 503 com mensagem clara (cliente precisa ativar)
        - Saldo insuficiente → 402 (Payment Required)
        - CNPJ inválido → 400
        - Erro genérico → 502
        """
        # ESTADUAL precisa de UF — usa empresa.uf
        uf = empresa.uf if tipo == "ESTADUAL" else None
        if tipo == "ESTADUAL" and not uf:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Empresa {empresa.cnpj} não tem UF cadastrada. "
                    "Edite o cadastro antes de consultar CND Estadual."
                ),
            )

        try:
            cnd, veio_do_cache = self.infosimples.cnd(
                cnpj=empresa.cnpj,
                tipo=tipo,  # type: ignore[arg-type]
                uf=uf,
                force=force,
            )
        except InfosimplesProdutoNaoHabilitado as exc:
            logger.error("Produto %s não habilitado: %s", tipo, exc)
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Produto '{tipo}' não está habilitado na sua conta Infosimples. "
                    f"Ative em https://infosimples.com/painel e tente de novo."
                ),
            ) from exc
        except InfosimplesSaldoInsuficiente as exc:
            logger.error("Sem saldo Infosimples: %s", exc)
            raise HTTPException(
                status_code=402,
                detail=(
                    "Saldo Infosimples insuficiente. Recarregue em "
                    "https://infosimples.com/painel e tente de novo."
                ),
            ) from exc
        except InfosimplesError as exc:
            logger.warning("Infosimples CND %s falhou para %s: %s", tipo, empresa.cnpj, exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # Baixa o PDF da CND se vier URL (e ainda não temos bytes)
        pdf_path_str: str | None = None
        if cnd.pdf_url:
            try:
                pdf_path_str = self._baixar_pdf_cnd(empresa.cnpj, tipo, cnd)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Falha ao baixar PDF (não bloqueia): %s", exc)

        # Validade: usa a retornada pelo Infosimples; se não vier, calcula
        # com a tabela padrão (FGTS=30d, CNDT=180d, FEDERAL=180d)
        validade = cnd.data_validade or (
            (cnd.data_emissao or date.today())
            + timedelta(days=VALIDADES_DIAS.get(tipo, 30))
        )
        emissao = cnd.data_emissao or date.today()
        numero = cnd.numero or f"INFOSIMPLES-{tipo}-{date.today().strftime('%Y%m%d')}"

        observacoes_partes = [
            f"Consultada via Infosimples ({'cache' if veio_do_cache else 'API real'})",
            f"Situação: {cnd.situacao}",
        ]
        if cnd.situacao == "irregular":
            observacoes_partes.append(
                "⚠ CND retornou IRREGULAR — verifique débitos pendentes no portal."
            )
        observacoes = ". ".join(observacoes_partes) + "."

        cert = Certidao(
            empresa_id=empresa.id,
            tipo=TipoCertidao(tipo),
            numero=numero,
            data_emissao=emissao,
            data_validade=validade,
            pdf_path=pdf_path_str,
            observacoes=observacoes,
        )
        self.db.add(cert)
        self.db.commit()
        self.db.refresh(cert)
        return cert

    def _baixar_pdf_cnd(
        self, cnpj: str, tipo: TipoCnd, cnd: CndInfosimples,
    ) -> str | None:
        """Baixa o PDF da URL retornada pelo Infosimples e salva no storage."""
        if not cnd.pdf_url:
            return None
        import requests
        try:
            resp = requests.get(cnd.pdf_url, timeout=60)
            resp.raise_for_status()
            content = resp.content
        except requests.RequestException as exc:
            logger.warning("Falha ao baixar PDF CND %s %s: %s", tipo, cnpj, exc)
            return None
        storage_root = Path(_settings.storage_path).parent / "cnds" / cnpj
        storage_root.mkdir(parents=True, exist_ok=True)
        suffix = (cnd.numero or "sem-numero")[-12:].replace("/", "-").replace(" ", "")
        filename = f"{tipo}_{date.today().strftime('%Y%m%d')}_{suffix}.pdf"
        pdf_path = storage_root / filename
        pdf_path.write_bytes(content)
        return str(pdf_path)

    # --- Legacy via portal (Playwright + 2captcha) — mantido como fallback
    #     mas NÃO chamado mais. Deletar quando migração estiver consolidada. ---

    def _renovar_via_sefaz(self, empresa: Empresa, tipo: TipoCnd) -> Certidao:
        """[DEPRECATED] Mantido só pra rollback emergencial. Não usar."""
        try:
            emitida: CndEmitida = self.provider.emitir_cnd(
                cnpj=empresa.cnpj, tipo=tipo,
                certificado_pfx=None, certificado_senha=None,
            )
        except SefazRobotError as exc:
            logger.warning("CND %s falhou para %s: %s", tipo, empresa.cnpj, exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        storage_root = Path(_settings.storage_path).parent / "cnds" / empresa.cnpj
        storage_root.mkdir(parents=True, exist_ok=True)
        filename = f"{tipo}_{emitida.data_emissao.strftime('%Y%m%d')}_{emitida.numero[-12:]}.pdf"
        pdf_path = storage_root / filename
        pdf_path.write_bytes(emitida.pdf_bytes)

        cert = Certidao(
            empresa_id=empresa.id,
            tipo=TipoCertidao(tipo),
            numero=emitida.numero,
            data_emissao=emitida.data_emissao,
            data_validade=emitida.data_validade,
            pdf_path=str(pdf_path),
            observacoes=f"[LEGACY] Emitida automaticamente via {emitida.portal}.",
        )
        self.db.add(cert)
        self.db.commit()
        self.db.refresh(cert)
        return cert

    # --- Renovacao em massa ---

    def renovar_vencendo(
        self,
        janela_dias: int = 7,
        tipos: tuple[str, ...] = ("FEDERAL", "FGTS"),
    ) -> RenovacaoResultado:
        """Renova automaticamente comprovantes vencendo em <= janela_dias OU vencidos.

        Defaults:
        - FEDERAL: gratuito (~R$ 0,03), uso interno mensal.
        - FGTS: ~R$ 0,20 via Infosimples, renovação mensal (validade 30d).

        NÃO inclui por padrão:
        - FEDERAL_OFICIAL: emitido sob demanda (licitação/banco pontuais).
        - ESTADUAL: precisa UF cadastrada na empresa — caller decide se quer.
        - TRABALHISTA: cadastro manual.
        Pra incluir, passe tipos=("FEDERAL", "FGTS", "ESTADUAL", ...).
        """
        hoje = date.today()
        limite = hoje + timedelta(days=janela_dias)
        resultado = RenovacaoResultado()

        empresas = self.db.scalars(
            select(Empresa).where(Empresa.ativo.is_(True)).order_by(Empresa.id)
        ).all()

        for empresa in empresas:
            for tipo in tipos:
                # Busca a CND mais recente desse tipo
                ultima = self.db.scalar(
                    select(Certidao)
                    .where(
                        Certidao.empresa_id == empresa.id,
                        Certidao.tipo == TipoCertidao(tipo),
                    )
                    .order_by(Certidao.data_validade.desc(), Certidao.id.desc())
                )
                # Se nao existe ou esta vencendo na janela: emitir
                deve_renovar = ultima is None or ultima.data_validade <= limite
                if not deve_renovar:
                    resultado.pulados += 1
                    continue
                try:
                    nova = self.renovar_cnd(empresa.id, tipo)  # type: ignore[arg-type]
                    resultado.sucesso += 1
                    resultado.detalhes.append({
                        "empresa_id": empresa.id,
                        "empresa_nome": empresa.razao_social,
                        "tipo": tipo,
                        "status": "ok",
                        "certidao_id": nova.id,
                        "validade_nova": nova.data_validade.isoformat(),
                    })
                except HTTPException as exc:
                    resultado.falhas += 1
                    resultado.detalhes.append({
                        "empresa_id": empresa.id,
                        "empresa_nome": empresa.razao_social,
                        "tipo": tipo,
                        "status": "erro",
                        "mensagem": str(exc.detail),
                    })
                except Exception as exc:  # noqa: BLE001
                    resultado.falhas += 1
                    logger.exception("Erro inesperado renovando CND")
                    resultado.detalhes.append({
                        "empresa_id": empresa.id,
                        "empresa_nome": empresa.razao_social,
                        "tipo": tipo,
                        "status": "erro_inesperado",
                        "mensagem": str(exc)[:200],
                    })
        return resultado
