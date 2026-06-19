"""Servico de apuracao mensal (PGDAS-D Simples Nacional + extensao futura)."""
from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.apuracao import Apuracao, RegimeApuracao, StatusApuracao
from app.models.empresa import Empresa
from app.providers.integra_contador import (
    IntegraContadorError,
    IntegraContadorProvider,
    parse_dados,
)


_settings = get_settings()


class ApuracaoService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = IntegraContadorProvider()

    # --- Acesso ---

    def get_or_404(self, apuracao_id: int) -> Apuracao:
        apur = self.db.get(Apuracao, apuracao_id)
        if not apur:
            raise HTTPException(status_code=404, detail="Apuracao nao encontrada")
        return apur

    def get_empresa_or_404(self, empresa_id: int) -> Empresa:
        empresa = self.db.get(Empresa, empresa_id)
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa nao encontrada")
        return empresa

    def listar(
        self,
        *,
        empresa_id: int | None = None,
        ano_mes: str | None = None,
    ) -> list[Apuracao]:
        stmt = select(Apuracao).order_by(Apuracao.ano_mes.desc(), Apuracao.id.desc())
        if empresa_id:
            stmt = stmt.where(Apuracao.empresa_id == empresa_id)
        if ano_mes:
            stmt = stmt.where(Apuracao.ano_mes == ano_mes)
        return list(self.db.scalars(stmt).all())

    # --- Criacao / DRAFT ---

    def criar_draft(
        self,
        empresa_id: int,
        ano_mes: str,
        receita_bruta: float,
        receitas_segregadas: list[dict] | None = None,
    ) -> Apuracao:
        empresa = self.get_empresa_or_404(empresa_id)
        # Idempotencia: se ja existir DRAFT/TRANSMITIDA/DAS_GERADO para esta competencia,
        # atualiza ao inves de criar nova.
        existente = self.db.scalar(
            select(Apuracao).where(
                Apuracao.empresa_id == empresa_id, Apuracao.ano_mes == ano_mes,
            )
        )
        regime = RegimeApuracao.SIMPLES_NACIONAL  # MVP
        if existente:
            existente.receita_bruta = Decimal(str(receita_bruta))
            existente.receitas_segregadas = receitas_segregadas or []
            existente.regime = regime
            self.db.commit()
            self.db.refresh(existente)
            return existente
        apur = Apuracao(
            empresa_id=empresa.id,
            ano_mes=ano_mes,
            regime=regime,
            status=StatusApuracao.DRAFT,
            receita_bruta=Decimal(str(receita_bruta)),
            receitas_segregadas=receitas_segregadas or [],
        )
        self.db.add(apur)
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Transmissao PGDAS-D ---

    def _receita_interna_externa(self, apur: Apuracao) -> tuple[float, float]:
        """Separa receita interna (normal+ST+monofásico+serviços) de externa
        (exportação) a partir do receitas_segregadas salvo pelo calculator."""
        externa = 0.0
        interna = 0.0
        for r in (apur.receitas_segregadas or []):
            valor = float(r.get("valor") or 0)
            if (r.get("natureza") or "").upper() == "EXPORTACAO":
                externa += valor
            else:
                interna += valor
        # Fallback: se não tem segregação, tudo interno
        if interna == 0 and externa == 0 and apur.receita_bruta:
            interna = float(apur.receita_bruta)
        return interna, externa

    def _atividades_segregadas(self, apur: Apuracao) -> list[dict]:
        """Monta atividades[] do PGDAS-D segregando por ATIVIDADE e QUALIFICAÇÃO.

        A RFB recusa ST/monofásico no idAtividade=1 (erro MSG_ISN_032), porque a
        qualificação depende da atividade (tabela de domínio Serpro):
          - idAtividade 1 = revenda de mercadorias SEM ST/monofásico;
          - idAtividade 2 = revenda de mercadorias COM ST/monofásico (aqui as
            qualificações 8=ST / 9=monofásico são permitidas).

        Então: receita NORMAL vai na atividade 1; ST/MONOFASICO/MONOFASICO_ST vão
        na atividade 2, cada receita com suas qualificacoesTributarias por tributo
        ({CodigoTributo, Id}). Tributos: 1004 COFINS, 1005 PIS, 1007 ICMS.

        Empresa SEM ST/monofásico → só a atividade 1 (qualif []), idêntico ao
        comportamento antigo. ⚠️ idAtividade 1/2 e estrutura confirmados por
        dry-run (Serpro guiou via MSG_ISN_036/032)."""
        COD_COFINS, COD_PIS, COD_ICMS = 1004, 1005, 1007
        QUAL_ST, QUAL_MONOFASICO = 8, 9

        def _qualif(cod_tributo: int, qual: int) -> dict:
            return {"CodigoTributo": cod_tributo, "Id": qual}

        def _receita(valor: float, quals: list[dict]) -> dict:
            return {
                "valor": round(valor, 2),
                "codigoOutroMunicipio": None,
                "outraUf": None,
                "qualificacoesTributarias": quals,
                "isencoes": [],
                "reducoes": [],
                "exigibilidadesSuspensas": None,
            }

        buckets: dict[str, float] = {}
        for r in (apur.receitas_segregadas or []):
            nat = (r.get("natureza") or "").upper()
            if nat == "EXPORTACAO":
                continue  # vai em receitaPaCompetenciaExterno, não aqui
            buckets[nat] = buckets.get(nat, 0.0) + float(r.get("valor") or 0)

        normal = buckets.get("NORMAL", 0.0) + buckets.get("SERVICO", 0.0)
        st = buckets.get("ST", 0.0)
        mono = buckets.get("MONOFASICO", 0.0)
        mono_st = buckets.get("MONOFASICO_ST", 0.0)

        atividades: list[dict] = []
        # Atividade 1 — revenda SEM ST/monofásico
        if normal > 0.005:
            atividades.append({
                "idAtividade": 1,
                "valorAtividade": round(normal, 2),
                "receitasAtividade": [_receita(normal, [])],
            })
        # Atividade 2 — revenda COM ST/monofásico (qualificações permitidas aqui)
        receitas2: list[dict] = []
        if st > 0.005:
            receitas2.append(_receita(st, [_qualif(COD_ICMS, QUAL_ST)]))
        if mono > 0.005:
            receitas2.append(_receita(mono, [
                _qualif(COD_COFINS, QUAL_MONOFASICO), _qualif(COD_PIS, QUAL_MONOFASICO),
            ]))
        if mono_st > 0.005:
            receitas2.append(_receita(mono_st, [
                _qualif(COD_COFINS, QUAL_MONOFASICO), _qualif(COD_PIS, QUAL_MONOFASICO),
                _qualif(COD_ICMS, QUAL_ST),
            ]))
        if receitas2:
            atividades.append({
                "idAtividade": 2,
                "valorAtividade": round(st + mono + mono_st, 2),
                "receitasAtividade": receitas2,
            })
        return atividades

    def _receitas_brutas_anteriores(self, empresa_id: int, ano_mes: str) -> list[dict]:
        """Monta receitasBrutasAnteriores[] do payload PGDAS-D a partir da
        tabela ReceitaMensal (faturamento dos 12 meses anteriores)."""
        from app.models.receita_mensal import ReceitaMensal
        from app.services.receita_mensal_service import meses_anteriores

        meses = meses_anteriores(ano_mes, 12)
        registros = {
            r.ano_mes: r for r in self.db.scalars(
                select(ReceitaMensal).where(
                    ReceitaMensal.empresa_id == empresa_id,
                    ReceitaMensal.ano_mes.in_(meses),
                )
            ).all()
        }
        out = []
        for am in meses:
            r = registros.get(am)
            if not r:
                continue
            out.append({
                "pa": int(am),
                "valorInterno": float(r.valor_interno or 0),
                "valorExterno": float(r.valor_externo or 0),
            })
        return out

    def transmitir(self, apuracao_id: int, *, dry_run: bool = True) -> dict:
        """Transmite (ou valida via dry-run) a declaração PGDAS-D.

        `dry_run=True` (default) → indicadorTransmissao=False: a RFB calcula e
        devolve os valores apurados SEM gerar declaração. Seguro pra conferir
        antes de transmitir de verdade.
        `dry_run=False` → transmite real, marca status=TRANSMITIDA, salva recibo.

        Retorna dict com {dry_run, valores_rfb, valor_devido_rfb, valor_pac,
        divergencia, apuracao}. Em dry-run NÃO altera o status da apuração.
        """
        apur = self.get_or_404(apuracao_id)
        if not apur.receita_bruta:
            raise HTTPException(
                status_code=400, detail="Receita bruta obrigatoria. Calcule a apuracao primeiro.",
            )
        empresa = self.get_empresa_or_404(apur.empresa_id)
        interna, externa = self._receita_interna_externa(apur)
        receitas_anteriores = self._receitas_brutas_anteriores(apur.empresa_id, apur.ano_mes)
        try:
            payload = self.provider.pgdas_transmitir_declaracao(
                empresa.cnpj,
                ano_mes=apur.ano_mes,
                receita_bruta=float(apur.receita_bruta),
                receita_interna=interna,
                receita_externa=externa,
                receitas_brutas_anteriores=receitas_anteriores,
                indicador_transmissao=not dry_run,
                atividades=self._atividades_segregadas(apur),
            )
        except IntegraContadorError as exc:
            if not dry_run:
                apur.status = StatusApuracao.ERRO
                self.db.commit()
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")

        dados = parse_dados(payload)
        # Valor devido apurado pela RFB. A Serpro NÃO devolve um total — devolve
        # o DAS POR TRIBUTO em `valoresDevidos` (1001 IRPJ, 1002 CSLL, 1004
        # COFINS, 1005 PIS, 1006 CPP, 1007 ICMS, 1008 ISS...). Soma pra ter o
        # total e poder comparar com o PAC.
        valor_rfb = dados.get("valorDevido")
        valores_rfb = dados.get("valoresDevidos") or []
        if valor_rfb is None and valores_rfb:
            valor_rfb = round(
                sum(float(v.get("valor") or 0) for v in valores_rfb), 2,
            )
        valor_pac = float(apur.valor_devido) if apur.valor_devido else None
        divergencia = None
        if valor_rfb is not None and valor_pac is not None:
            divergencia = round(float(valor_rfb) - valor_pac, 2)

        if not dry_run:
            # Transmissão REAL: persiste
            apur.numero_declaracao = dados.get("numeroDeclaracao")
            apur.recibo = dados.get("recibo")
            if valor_rfb is not None:
                apur.valor_devido = Decimal(str(valor_rfb))
            apur.transmitida_em = datetime.now(timezone.utc)
            apur.status = StatusApuracao.TRANSMITIDA
            apur.raw_declaracao = dados
            self.db.commit()
            self.db.refresh(apur)

        return {
            "dry_run": dry_run,
            "valor_devido_rfb": valor_rfb,
            "valores_rfb": valores_rfb,
            "valor_devido_pac": valor_pac,
            "divergencia": divergencia,
            "raw": dados,
            "apuracao_id": apur.id,
            "status": apur.status.value,
        }

    # --- Geracao DAS ---

    def gerar_das(self, apuracao_id: int) -> Apuracao:
        apur = self.get_or_404(apuracao_id)
        if apur.status not in (StatusApuracao.TRANSMITIDA, StatusApuracao.DAS_GERADO):
            raise HTTPException(
                status_code=400,
                detail="Transmita a declaracao antes de gerar o DAS.",
            )
        empresa = self.get_empresa_or_404(apur.empresa_id)
        try:
            payload = self.provider.pgdas_gerar_das(empresa.cnpj, ano_mes=apur.ano_mes)
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        dados = parse_dados(payload)
        pdf_b64 = dados.get("pdf") or ""
        if not pdf_b64:
            raise HTTPException(status_code=502, detail="DAS sem PDF retornado.")
        # Salvar PDF
        storage_root = Path(_settings.storage_path).parent / "apuracoes"
        empresa_dir = storage_root / empresa.cnpj
        empresa_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        pdf_path = empresa_dir / f"das_{apur.ano_mes}_{ts}.pdf"
        try:
            pdf_path.write_bytes(base64.b64decode(pdf_b64))
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"PDF DAS invalido: {exc}"
            ) from exc
        apur.das_numero_documento = dados.get("numeroDocumento")
        apur.das_codigo_barras = dados.get("codigoBarras")
        apur.das_data_vencimento = dados.get("dataVencimento")
        apur.das_pdf_path = str(pdf_path)
        valor = dados.get("valorTotal")
        if valor:
            apur.valor_devido = Decimal(str(valor))
        apur.status = StatusApuracao.DAS_GERADO
        # Remove o pdf do raw para nao inflar JSON (mantem so metadados)
        apur.raw_das = {k: v for k, v in dados.items() if k != "pdf"}
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Marcacao manual de pagamento ---

    def marcar_pago(self, apuracao_id: int) -> Apuracao:
        apur = self.get_or_404(apuracao_id)
        apur.status = StatusApuracao.PAGO
        self.db.commit()
        self.db.refresh(apur)
        return apur

    # --- Extrato detalhado (CONSEXTRATO16) ---

    def consultar_extrato(self, apuracao_id: int) -> dict[str, Any]:
        apur = self.get_or_404(apuracao_id)
        empresa = self.get_empresa_or_404(apur.empresa_id)
        try:
            payload = self.provider.pgdas_consultar_extrato(
                empresa.cnpj, ano_mes=apur.ano_mes,
            )
        except IntegraContadorError as exc:
            raise HTTPException(status_code=502, detail=f"Integra Contador: {exc}")
        return parse_dados(payload)

    # --- Resumo do mes (todas empresas) ---

    def resumo_mes(self, ano_mes: str) -> dict[str, Any]:
        apuracoes = self.listar(ano_mes=ano_mes)
        empresas_ativas = self.db.scalars(
            select(Empresa).where(Empresa.ativo.is_(True))
        ).all()

        empresas_apuradas = {a.empresa_id for a in apuracoes}
        pendentes = [e for e in empresas_ativas if e.id not in empresas_apuradas]
        valor_total = sum(
            (a.valor_devido or Decimal(0)) for a in apuracoes
        )
        valor_pago = sum(
            (a.valor_devido or Decimal(0))
            for a in apuracoes
            if a.status == StatusApuracao.PAGO
        )
        return {
            "ano_mes": ano_mes,
            "total_empresas_ativas": len(empresas_ativas),
            "apuracoes_geradas": len(apuracoes),
            "pendentes": len(pendentes),
            "transmitidas": sum(1 for a in apuracoes if a.status in (
                StatusApuracao.TRANSMITIDA, StatusApuracao.DAS_GERADO, StatusApuracao.PAGO
            )),
            "das_gerados": sum(1 for a in apuracoes if a.status in (
                StatusApuracao.DAS_GERADO, StatusApuracao.PAGO
            )),
            "pagos": sum(1 for a in apuracoes if a.status == StatusApuracao.PAGO),
            "valor_devido_total": float(valor_total),
            "valor_pago": float(valor_pago),
            "empresas_pendentes": [
                {"id": e.id, "razao_social": e.razao_social, "cnpj": e.cnpj}
                for e in pendentes[:20]
            ],
        }
