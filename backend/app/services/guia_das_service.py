"""Serviço de gestão das guias DAS Simples Nacional.

Fluxo de sync por empresa:
1. `sync_empresa(empresa_id, ano)` chama PGDASD CONSDECREC13 → lista declarações
2. Pra cada competência, cria/atualiza linha em `guias_das` (upsert por unique)
3. Chama PAGTOWEB PAGAMENTOS71 no mesmo período → marca pagas
4. Empresas com vencimento expirado e sem pagamento viram `situacao='atrasada'`

Emissão de guia atualizada (caminho #18):
- `emitir_guia_atualizada(guia_id)` → chama PGDASD GERARDAS12, a Serpro retorna
  PDF base64 com valor já corrigido (Selic+multa). Salva em
  `storage/guias/{cnpj}/das_{periodo}_{timestamp}.pdf`.

Idempotência: unique (empresa_id, periodo_apuracao). Pagamento parcial
detectado quando `valor_pago < valor_principal`.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from app.models.empresa import Empresa
from app.models.guia_das import GuiaDAS
from app.providers.integra_contador import (
    IntegraContadorError,
    IntegraContadorProvider,
    parse_dados,
)

logger = logging.getLogger(__name__)

# Onde salvar PDFs das guias emitidas (mesmo padrão de storage/xmls).
STORAGE_GUIAS = Path(os.getenv("STORAGE_GUIAS_DIR", "./storage/guias")).resolve()


@dataclass(slots=True)
class SyncDASResultado:
    novas: int = 0
    atualizadas: int = 0
    pagas_detectadas: int = 0
    erros: int = 0
    detalhes: list[dict] | None = None


class GuiaDASService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = IntegraContadorProvider()

    # ------------------------------------------------------------------
    # Sync (caminho #17)
    # ------------------------------------------------------------------
    def sync_empresa(self, empresa_id: int, *, ano: int) -> SyncDASResultado:
        """Sincroniza declarações + pagamentos de um ano específico.

        Não emite guia atualizada (isso é #18, via `emitir_guia_atualizada`).
        """
        empresa = self.db.get(Empresa, empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {empresa_id} não encontrada")

        resultado = SyncDASResultado(detalhes=[])

        try:
            resp = self.provider.pgdas_listar_declaracoes(
                empresa.cnpj, ano=str(ano),
            )
        except IntegraContadorError as exc:
            logger.error(
                "Falha ao listar declarações empresa=%s ano=%s: %s",
                empresa_id, ano, exc,
            )
            resultado.erros += 1
            resultado.detalhes.append(  # type: ignore[union-attr]
                {"erro": str(exc)[:300], "etapa": "listar_declaracoes"},
            )
            return resultado

        dados = parse_dados(resp)
        # Estrutura real Serpro (CONSDECLARACAO13):
        # {anoCalendario, periodos: [{periodoApuracao, operacoes: [...]}]}
        periodos = dados.get("periodos") or []

        for periodo_info in periodos:
            try:
                guia, foi_nova, foi_paga = self._upsert_periodo(
                    empresa_id, empresa.cnpj, periodo_info,
                )
                if guia is None:
                    continue
                if foi_nova:
                    resultado.novas += 1
                else:
                    resultado.atualizadas += 1
                if foi_paga:
                    resultado.pagas_detectadas += 1
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha ao upsert período %s", periodo_info)
                resultado.erros += 1
                resultado.detalhes.append(  # type: ignore[union-attr]
                    {
                        "erro": str(exc)[:300],
                        "competencia": str(periodo_info.get("periodoApuracao")),
                    },
                )

        # Garante que as guias acabadas de inserir/atualizar estão visíveis
        # ao SELECT do _marcar_atrasadas (autoflush nem sempre garante ordem).
        self.db.flush()
        # Atualiza situação `em_aberto` → `atrasada` para vencidas sem pagamento
        self._marcar_atrasadas(empresa_id=empresa_id)
        self.db.commit()
        return resultado

    def sync_todas_empresas_simples(self, ano: int) -> dict[int, SyncDASResultado]:
        """Roda `sync_empresa` para todas as empresas ATIVAS + Simples Nacional."""
        empresas = self.db.scalars(
            select(Empresa).where(
                Empresa.ativo.is_(True),
                or_(
                    Empresa.regime_tributario.ilike("%simples%"),
                    Empresa.tributacao.ilike("%simples%"),
                ),
            ).order_by(Empresa.id),
        ).all()
        out: dict[int, SyncDASResultado] = {}
        for emp in empresas:
            try:
                out[emp.id] = self.sync_empresa(emp.id, ano=ano)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Falha total sync empresa %s", emp.id)
                out[emp.id] = SyncDASResultado(erros=1, detalhes=[{"erro": str(exc)[:300]}])
        return out

    # ------------------------------------------------------------------
    # Emissão de guia atualizada (caminho #18)
    # ------------------------------------------------------------------
    def emitir_guia_atualizada(self, guia_id: int) -> GuiaDAS:
        """Gera nova DARF com valor corrigido (Selic+mora) via Integra Contador.

        - Se DAS atrasada (vencimento < hoje): usa **GERARDASCOBRANCA17**, que
          busca o débito no sistema de Cobrança RFB já com Selic+multa+juros
          atualizados até hoje.
        - Se ainda no prazo: usa **GERARDAS12** (DAS normal, sem mora).

        Salva o PDF em `storage/guias/{cnpj}/das_{periodo}_{ts}.pdf` e atualiza
        a linha em `guias_das` com valor + vencimento + caminho do PDF.
        """
        guia = self.db.get(GuiaDAS, guia_id)
        if guia is None:
            raise ValueError(f"Guia DAS {guia_id} não encontrada")
        empresa = self.db.get(Empresa, guia.empresa_id)
        if empresa is None:
            raise ValueError(f"Empresa {guia.empresa_id} (da guia) não encontrada")

        # Escolhe endpoint baseado na situação: cobrança RFB se atrasada,
        # GERARDAS12 normal se ainda no prazo.
        if guia.situacao in {"atrasada", "parcialmente_paga"}:
            logger.info("Guia %s atrasada → GERARDASCOBRANCA17", guia_id)
            resp = self.provider.pgdas_gerar_das_cobranca(
                empresa.cnpj, ano_mes=guia.periodo_apuracao,
            )
        else:
            logger.info("Guia %s no prazo → GERARDAS12", guia_id)
            resp = self.provider.pgdas_gerar_das(
                empresa.cnpj, ano_mes=guia.periodo_apuracao,
            )
        dados = parse_dados(resp)

        pdf_b64 = dados.get("pdf")
        if not pdf_b64:
            raise IntegraContadorError(
                "PDF não retornado pela Serpro (GERARDAS12)",
                codigo="SEM_PDF",
            )

        # Salva PDF em storage/guias/{cnpj}/das_{periodo}_{ts}.pdf
        cnpj_clean = "".join(c for c in empresa.cnpj if c.isdigit())
        dest_dir = STORAGE_GUIAS / cnpj_clean
        dest_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = dest_dir / f"das_{guia.periodo_apuracao}_{ts}.pdf"
        try:
            dest_path.write_bytes(base64.b64decode(pdf_b64))
        except Exception as exc:
            raise IntegraContadorError(
                f"Falha ao salvar PDF: {exc!r}", codigo="PDF_WRITE",
            ) from exc

        # Estrutura real Serpro GERARDASCOBRANCA17:
        #   {pdf, cnpjCompleto, detalhamentoDas: {valores: {principal, multa, juros, total},
        #    numeroDocumento, dataVencimento, dataLimiteAcolhimento}}
        # GERARDAS12 (DAS normal) talvez devolva flat — tentamos os dois layouts.
        detalhe = dados.get("detalhamentoDas") or dados
        valores = detalhe.get("valores") or {}

        total = valores.get("total") if isinstance(valores, dict) else None
        if total is None:
            total = dados.get("valorTotal") or detalhe.get("valorTotal")

        guia.valor_atualizado = self._d(total)
        guia.numero_das = (
            (detalhe.get("numeroDocumento") or dados.get("numeroDocumento") or "")[:32]
            or None
        )
        guia.codigo_barras = (
            (detalhe.get("codigoBarras") or dados.get("codigoBarras") or "")[:64]
            or None
        )
        # dataLimiteAcolhimento (preferido pra atrasadas) ou dataVencimento
        venc_raw = (
            detalhe.get("dataLimiteAcolhimento")
            or detalhe.get("dataVencimento")
            or dados.get("dataVencimento")
        )
        venc = self._d_date(venc_raw)
        if venc:
            guia.data_vencimento_atualizada = venc
        guia.pdf_path = str(dest_path)
        guia.emitida_em = datetime.now()
        self.db.commit()
        self.db.refresh(guia)
        logger.info(
            "Guia DAS %s atualizada: valor=%s venc=%s pdf=%s",
            guia.id, guia.valor_atualizado, guia.data_vencimento_atualizada, dest_path,
        )
        return guia

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def listar_empresa(
        self, empresa_id: int, *, somente_atrasadas: bool = False,
    ) -> list[GuiaDAS]:
        stmt = (
            select(GuiaDAS)
            .where(GuiaDAS.empresa_id == empresa_id)
            .order_by(desc(GuiaDAS.periodo_apuracao))
        )
        if somente_atrasadas:
            stmt = stmt.where(GuiaDAS.situacao == "atrasada")
        return list(self.db.scalars(stmt).all())

    def dashboard_atrasadas(self) -> list[GuiaDAS]:
        """Todas as guias atrasadas, ordenadas por dias de atraso desc.

        Útil pra a UI de cobrança: 1 view global cruzando todas as empresas.
        """
        stmt = (
            select(GuiaDAS)
            .where(GuiaDAS.situacao == "atrasada")
            .order_by(GuiaDAS.data_vencimento_original.asc())
        )
        return list(self.db.scalars(stmt).all())

    def obter(self, guia_id: int) -> GuiaDAS | None:
        return self.db.get(GuiaDAS, guia_id)

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------
    def _upsert_periodo(
        self, empresa_id: int, cnpj: str, periodo_info: dict[str, Any],
    ) -> tuple[GuiaDAS | None, bool, bool]:
        """Processa um período retornado por CONSDECLARACAO13.

        Estrutura real Serpro:
            {periodoApuracao: 202501, operacoes: [
              {tipoOperacao: 'Original', indiceDeclaracao: {numeroDeclaracao, dataHoraTransmissao, malha}},
              {tipoOperacao: 'Geração de DAS', indiceDas: {numeroDas, datahoraEmissaoDas, dasPago: bool}}
            ]}

        Retorna `(guia, foi_nova, foi_paga_agora)`.
        """
        pa = periodo_info.get("periodoApuracao")
        if pa is None:
            return None, False, False
        competencia = str(pa)  # int → str "202501"
        if len(competencia) != 6:
            logger.warning("periodoApuracao inválido: %r", pa)
            return None, False, False

        # Extrai info das operações
        numero_declaracao: str | None = None
        numero_das: str | None = None
        data_transmissao: datetime | None = None
        das_pago = False
        for op in periodo_info.get("operacoes") or []:
            tipo = (op.get("tipoOperacao") or "").lower()
            if "original" in tipo or "declar" in tipo:
                idc = op.get("indiceDeclaracao") or {}
                numero_declaracao = (idc.get("numeroDeclaracao") or "")[:64] or numero_declaracao
                data_transmissao = self._d_datetime_serpro(idc.get("dataHoraTransmissao")) or data_transmissao
            das = op.get("indiceDas")
            if das:
                if das.get("dasPago") is True:
                    das_pago = True
                num = das.get("numeroDas")
                if num and not numero_das:
                    numero_das = str(num)[:32]

        # Busca valor via CONSEXTRATO16 usando o numeroDas (vem do indiceDas)
        valor = Decimal("0.00")
        if numero_das:
            try:
                ext_resp = self.provider.pgdas_consultar_extrato_das(
                    cnpj, numero_das=numero_das,
                )
                ext_dados = parse_dados(ext_resp)
                v = (
                    ext_dados.get("valorTotalDevido")
                    or ext_dados.get("valorTotal")
                    or ext_dados.get("valorDevido")
                )
                if v is not None:
                    valor = self._d(v)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Falha CONSEXTRATO16 cnpj=%s numDas=%s: %s",
                    cnpj, numero_das, exc,
                )

        venc = self._vencimento_das(competencia)

        existente = self.db.scalar(
            select(GuiaDAS).where(
                GuiaDAS.empresa_id == empresa_id,
                GuiaDAS.periodo_apuracao == competencia,
            ),
        )

        # Lógica de situação
        nova_situacao = "paga" if das_pago else (
            "atrasada" if venc < date.today() else "em_aberto"
        )

        if existente:
            ja_era_paga = existente.situacao == "paga"
            existente.valor_principal = valor
            existente.data_vencimento_original = venc
            existente.numero_declaracao = numero_declaracao
            if numero_das and not existente.numero_das:
                existente.numero_das = numero_das
            if data_transmissao:
                existente.data_transmissao = data_transmissao
            existente.situacao = nova_situacao
            if das_pago and not existente.data_pagamento:
                existente.data_pagamento = date.today()
                existente.valor_pago = valor
            existente.sincronizada_em = datetime.now()
            foi_paga_agora = das_pago and not ja_era_paga
            return existente, False, foi_paga_agora

        nova = GuiaDAS(
            empresa_id=empresa_id,
            periodo_apuracao=competencia,
            numero_declaracao=numero_declaracao,
            numero_das=numero_das,
            data_transmissao=data_transmissao,
            valor_principal=valor,
            data_vencimento_original=venc,
            situacao=nova_situacao,
        )
        if das_pago:
            nova.data_pagamento = date.today()
            nova.valor_pago = valor
        self.db.add(nova)
        return nova, True, das_pago

    @staticmethod
    def _d_datetime_serpro(s: Any) -> datetime | None:
        """Aceita formato Serpro YYYYMMDDhhmmss (ex: '20250211142814')."""
        if not s:
            return None
        s = str(s)
        if len(s) == 14 and s.isdigit():
            try:
                return datetime.strptime(s, "%Y%m%d%H%M%S")
            except ValueError:
                pass
        # Fallback para o parser genérico
        return GuiaDASService._d_datetime(s)

    def _marcar_pagamentos(self, empresa_id: int, pagamentos: list[dict]) -> int:
        """Cruza pagamentos com guias_das em aberto. Match: valor + data próxima.

        Heurística MVP — uma pendência: pagamento de DAS Simples no PAGAMENTOS71
        deveria vir com `codigoReceita` próprio (não vi no mock). Sem catálogo
        confirmado, uso `descricaoReceita` contendo 'SIMPLES' OU 'DAS'.

        TODO: confirmar código de receita exato pro DAS Simples Nacional na doc
        Serpro e filtrar por código.
        """
        marcadas = 0
        for pgto in pagamentos:
            descricao = (pgto.get("descricaoReceita") or "").upper()
            if "SIMPLES" not in descricao and "DAS" not in descricao:
                continue
            valor_pago = self._d(pgto.get("valorTotal"))
            data_pgto = self._d_date(pgto.get("dataArrecadacao"))
            if not data_pgto or not valor_pago:
                continue
            # Match: guia com vencimento no mesmo mês do pagamento e situacao != paga
            mes_pgto = data_pgto.strftime("%Y%m")
            guia = self.db.scalar(
                select(GuiaDAS).where(
                    GuiaDAS.empresa_id == empresa_id,
                    GuiaDAS.periodo_apuracao == mes_pgto,
                    GuiaDAS.situacao != "paga",
                ),
            )
            if not guia:
                continue
            guia.data_pagamento = data_pgto
            guia.valor_pago = valor_pago
            if valor_pago >= guia.valor_principal * Decimal("0.99"):
                guia.situacao = "paga"
            else:
                guia.situacao = "parcialmente_paga"
            marcadas += 1
        return marcadas

    def _marcar_atrasadas(self, *, empresa_id: int | None = None) -> int:
        """Atualiza `em_aberto` → `atrasada` quando vencimento < hoje."""
        hoje = date.today()
        stmt = select(GuiaDAS).where(
            GuiaDAS.situacao == "em_aberto",
            GuiaDAS.data_vencimento_original < hoje,
        )
        if empresa_id is not None:
            stmt = stmt.where(GuiaDAS.empresa_id == empresa_id)
        atrasadas = list(self.db.scalars(stmt).all())
        for g in atrasadas:
            g.situacao = "atrasada"
        return len(atrasadas)

    # --- Conversões de tipos defensivas ---

    @staticmethod
    def _d(valor: Any) -> Decimal:
        if valor is None or valor == "":
            return Decimal("0.00")
        try:
            return Decimal(str(valor))
        except Exception:
            return Decimal("0.00")

    @staticmethod
    def _d_date(s: Any) -> date | None:
        if not s:
            return None
        if isinstance(s, date):
            return s
        s = str(s)
        # Aceita "YYYY-MM-DD", "DD/MM/YYYY" e "YYYYMMDD" (formato Serpro)
        try:
            if "/" in s:
                return datetime.strptime(s[:10], "%d/%m/%Y").date()
            if "-" in s:
                return datetime.strptime(s[:10], "%Y-%m-%d").date()
            if len(s) == 8 and s.isdigit():
                return datetime.strptime(s, "%Y%m%d").date()
        except Exception:
            pass
        return None

    @staticmethod
    def _d_datetime(s: Any) -> datetime | None:
        if not s:
            return None
        if isinstance(s, datetime):
            return s
        s = str(s)
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s[: len(fmt) - fmt.count("%") + 2], fmt)
            except Exception:
                continue
        return None

    @staticmethod
    def _vencimento_das(competencia: str) -> date:
        """Vencimento padrão do DAS Simples Nacional: dia 20 do mês SEGUINTE
        à competência. Ex: competência 202604 → vencimento 20/05/2026.

        Quando dia 20 cair em fim de semana, Receita prorroga para o próximo
        dia útil — esse refinamento fica como TODO; pro MVP usamos dia 20 puro.
        """
        ano = int(competencia[:4])
        mes = int(competencia[4:])
        mes_venc = mes + 1
        ano_venc = ano
        if mes_venc > 12:
            mes_venc = 1
            ano_venc = ano + 1
        return date(ano_venc, mes_venc, 20)
