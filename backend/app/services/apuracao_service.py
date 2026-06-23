"""Servico de apuracao mensal (PGDAS-D Simples Nacional + extensao futura)."""
from __future__ import annotations

import base64
import re
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

    def _buckets_from_flat(self, apur: Apuracao) -> dict[str, float]:
        """Buckets {NATUREZA: valor} a partir do receitas_segregadas achatado
        (total da empresa). Exclui EXPORTACAO (vai em receitaPaCompetenciaExterno)."""
        buckets: dict[str, float] = {}
        for r in (apur.receitas_segregadas or []):
            nat = (r.get("natureza") or "").upper()
            if nat == "EXPORTACAO":
                continue
            buckets[nat] = buckets.get(nat, 0.0) + float(r.get("valor") or 0)
        return buckets

    def _atividades_segregadas(
        self, apur: Apuracao, anexo: str | None = None, anexo_servico: str | None = None,
    ) -> list[dict]:
        """atividades[] do PGDAS-D a partir dos totais achatados da empresa
        (caminho de estabelecimento único — sem filial). Sem regressão."""
        return self._buckets_to_atividades(self._buckets_from_flat(apur), anexo, anexo_servico)

    @staticmethod
    def _id_atividade_servico(anexo_serv: str) -> int:
        """idAtividade da atividade de SERVIÇO no payload PGDAS-D (empresa mista).
        Configurável por env (`PGDASD_IDATIV_SERV_III/IV/V`) pra iterar via dry-run
        sem novo deploy — só Restart. Default = hipótese (3/4/5), corrigida pela
        resposta da RFB (igual o #92 foi descoberto)."""
        import os
        default = {"III": 3, "IV": 4, "V": 5}.get(anexo_serv, 3)
        try:
            return int(os.getenv(f"PGDASD_IDATIV_SERV_{anexo_serv}", str(default)))
        except ValueError:
            return default

    def _buckets_to_atividades(
        self, buckets: dict[str, float], anexo: str | None = None,
        anexo_servico: str | None = None,
    ) -> list[dict]:
        """Monta atividades[] do PGDAS-D segregando por ATIVIDADE e QUALIFICAÇÃO.

        A RFB recusa ST/monofásico no idAtividade=1 (erro MSG_ISN_032), porque a
        qualificação depende da atividade (tabela de domínio Serpro):
          - idAtividade 1 = revenda de mercadorias SEM ST/monofásico;
          - idAtividade 2 = revenda de mercadorias COM ST/monofásico (aqui as
            qualificações 8=ST / 9=monofásico são permitidas).

        Então: receita NORMAL vai na atividade 1; ST/MONOFASICO/MONOFASICO_ST vão
        na atividade 2, cada receita com suas qualificacoesTributarias por tributo
        ({CodigoTributo, Id}). Tributos: 1004 COFINS, 1005 PIS, 1007 ICMS.

        Recebe os `buckets` {NORMAL, SERVICO, ST, MONOFASICO, MONOFASICO_ST} — pode
        ser o total da empresa (estab único) ou de UM estabelecimento (filial).
        Buckets todos zerados → atividades=[] (estabelecimento sem movimento).
        ⚠️ idAtividade 1/2 e estrutura confirmados por dry-run (MSG_ISN_036/032)."""
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

        # Serviço só é RECEITA do Simples nos Anexos III/IV/V (igual o motor faz em
        # apuracao_calculator). Em comércio/indústria (I/II) o motor IGNORA serviço
        # → o payload TAMBÉM tem que ignorar, senão a RFB taxa o serviço como
        # revenda e diverge (foi o caso AGIMED: RFB 8.848 × PAC 5.141). anexo=None
        # (legado, sem info) = conservador, NÃO inclui serviço.
        anx = (anexo or "").upper()
        servico = (buckets.get("SERVICO", 0.0) or 0.0) if anx in {"III", "IV", "V"} else 0.0
        normal = (buckets.get("NORMAL", 0.0) or 0.0) + servico
        st = buckets.get("ST", 0.0) or 0.0
        mono = buckets.get("MONOFASICO", 0.0) or 0.0
        mono_st = buckets.get("MONOFASICO_ST", 0.0) or 0.0

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
        # EMPRESA MISTA — atividade de SERVIÇO (Anexo III/IV/V), separada do
        # comércio. Sem isto a soma das atividades (só comércio) ≠ receita total
        # (que inclui serviço) → MSG_ISN_021. O serviço NÃO está em `normal` acima
        # (anx=I não é serviço), então entra aqui com sua própria idAtividade.
        anx_serv = (anexo_servico or "").upper()
        servico_misto = (buckets.get("SERVICO", 0.0) or 0.0)
        if anx_serv in {"III", "IV", "V"} and anx not in {"III", "IV", "V"} and servico_misto > 0.005:
            atividades.append({
                "idAtividade": self._id_atividade_servico(anx_serv),
                "valorAtividade": round(servico_misto, 2),
                "receitasAtividade": [_receita(servico_misto, [])],
            })
        return atividades

    @staticmethod
    def _so_digitos(s: str | None) -> str:
        return "".join(ch for ch in (s or "") if ch.isdigit())

    def _estabelecimentos_payload(
        self, apur: Apuracao, empresa: Empresa, extra_zero: list[str] | None = None,
    ) -> list[dict] | None:
        """Monta estabelecimentos[] (matriz + filiais) pro PGDAS-D.

        - Lê a quebra por estabelecimento que o motor gravou em raw_declaracao
          (receita das notas de cada CNPJ emitente).
        - RECONCILIA a matriz com os totais achatados (matriz = total − filiais),
          garantindo que a soma feche com receitaPaCompetenciaInterno.
        - `extra_zero`: filiais que a RFB exige (MSG_ISN_018) mas o PAC não tem
          nota → entram ZERADAS (atividades=[]).

        Retorna None quando só há a matriz e sem extras → o chamador usa o caminho
        antigo (estabelecimento único), sem regressão pra empresa sem filial.
        """
        matriz = self._so_digitos(empresa.cnpj)
        raw = apur.raw_declaracao or {}
        por_estab: dict[str, dict[str, float]] = {}
        for e in (raw.get("estabelecimentos") or []):
            c = self._so_digitos(e.get("cnpj"))
            if not c:
                continue
            por_estab[c] = {k: float(v or 0) for k, v in (e.get("buckets") or {}).items()}

        for f in (extra_zero or []):
            fc = self._so_digitos(f)
            if fc and fc != matriz:
                por_estab.setdefault(fc, {})

        por_estab.setdefault(matriz, {})

        # Só a matriz e nada exigido → caminho antigo (estab único).
        if list(por_estab.keys()) == [matriz] and not extra_zero:
            return None

        # Reconcilia a matriz = total achatado − soma das filiais (por natureza),
        # pra soma dos estabelecimentos casar EXATAMENTE com os totais da empresa.
        flat = self._buckets_from_flat(apur)
        naturezas = ["NORMAL", "MONOFASICO", "ST", "MONOFASICO_ST", "SERVICO"]
        soma_filiais = {n: 0.0 for n in naturezas}
        for c, b in por_estab.items():
            if c == matriz:
                continue
            for n in naturezas:
                soma_filiais[n] += float(b.get(n, 0) or 0)
        matriz_b: dict[str, float] = {}
        for n in naturezas:
            v = round(float(flat.get(n, 0) or 0) - soma_filiais[n], 2)
            matriz_b[n] = v if v > 0 else 0.0
        por_estab[matriz] = matriz_b

        ordem = [matriz] + [c for c in por_estab if c != matriz]
        return [
            {"cnpjCompleto": c, "atividades": self._buckets_to_atividades(por_estab.get(c, {}), empresa.anexo_simples, empresa.anexo_servico)}
            for c in ordem
        ]

    @staticmethod
    def _parse_estab_faltantes(msg: str | None) -> list[str]:
        """Extrai os CNPJs (14 díg.) que a RFB acusou faltando em estabelecimentos[]
        no erro MSG_ISN_018. A própria Receita diz quem falta → fonte de verdade."""
        if not msg or "MSG_ISN_018" not in msg:
            return []
        # dedupe preservando ordem
        vistos: list[str] = []
        for c in re.findall(r"\d{14}", msg):
            if c not in vistos:
                vistos.append(c)
        return vistos

    def _receitas_brutas_anteriores(self, empresa_id: int, ano_mes: str) -> list[dict]:
        """Monta receitasBrutasAnteriores[] do payload PGDAS-D (faturamento dos 12
        meses anteriores).

        ⚠️ TEM que bater com o RBT12 que o motor usa (apuracao_calculator._rbt12),
        senão a Receita cai numa FAIXA diferente e o DAS diverge (ex.: motor Faixa 5
        2,35M × RFB Faixa 4 1,17M = DAS subestimado). Por isso usa a MESMA prioridade
        de fonte por mês: ReceitaMensal (manual/Receita) e, na falta, a Apuração
        salva daquele mês (derivada das NFes). Antes ia SÓ ReceitaMensal → os meses
        que só tinham Apuração ficavam de fora e o RBT12 enviado vinha menor."""
        from app.models.receita_mensal import ReceitaMensal
        from app.services.receita_mensal_service import meses_anteriores

        meses = meses_anteriores(ano_mes, 12)
        receitas = {
            r.ano_mes: r for r in self.db.scalars(
                select(ReceitaMensal).where(
                    ReceitaMensal.empresa_id == empresa_id,
                    ReceitaMensal.ano_mes.in_(meses),
                )
            ).all()
        }
        apuracoes = {
            a.ano_mes: a for a in self.db.scalars(
                select(Apuracao).where(
                    Apuracao.empresa_id == empresa_id,
                    Apuracao.ano_mes.in_(meses),
                )
            ).all()
        }
        out = []
        for am in meses:
            r = receitas.get(am)
            if r is not None:
                interno = float(r.valor_interno or 0)
                externo = float(r.valor_externo or 0)
            else:
                a = apuracoes.get(am)
                if a is None or not a.receita_bruta:
                    continue
                # Apuração não separa interno/externo → tudo em interno (a FAIXA do
                # RBT12 usa o total interno+externo, então não muda o enquadramento).
                interno = float(a.receita_bruta)
                externo = 0.0
            if interno <= 0 and externo <= 0:
                continue
            out.append({"pa": int(am), "valorInterno": interno, "valorExterno": externo})
        return out

    # Tolerância de divergência PAC × RFB pra liberar a transmissão real. Centavos
    # de arredondamento são normais (dry-runs reais bateram a R$0,02-0,03); acima
    # disso é erro de payload/receita e NÃO se transmite sem revisar.
    TOLERANCIA_DIVERGENCIA = 1.00

    def transmitir(self, apuracao_id: int, *, dry_run: bool = True, forcar: bool = False) -> dict:
        """Transmite (ou valida via dry-run) a declaração PGDAS-D.

        `dry_run=True` (default) → indicadorTransmissao=False: a RFB calcula e
        devolve os valores apurados SEM gerar declaração. Seguro pra conferir
        antes de transmitir de verdade.
        `dry_run=False` → transmite real, marca status=TRANSMITIDA, salva recibo.

        TRAVA DE SEGURANÇA (alto risco fiscal): a transmissão REAL faz um dry-run
        ANTES e SÓ prossegue se PAC × RFB baterem (divergência ≤ tolerância). Se
        divergirem, levanta 409 com os números e NÃO transmite — a não ser que
        `forcar=True` (admin assume, após revisar). Isso protege todos os casos,
        incluindo o `idAtividade` de serviço ainda não validado por dry-run real.

        Retorna dict com {dry_run, valores_rfb, valor_devido_rfb, valor_pac,
        divergencia, apuracao}. Em dry-run NÃO altera o status da apuração.
        """
        apur = self.get_or_404(apuracao_id)
        if not apur.receita_bruta:
            raise HTTPException(
                status_code=400, detail="Receita bruta obrigatoria. Calcule a apuracao primeiro.",
            )

        # GUARDA: nunca transmite REAL sem um dry-run que bata com a RFB.
        if not dry_run and not forcar:
            previa = self.transmitir(apuracao_id, dry_run=True)
            div = previa.get("divergencia")
            if div is None:
                raise HTTPException(status_code=409, detail={
                    "erro": "sem_comparacao",
                    "mensagem": (
                        "Não dá pra comparar PAC × RFB (apuração sem valor calculado). "
                        "Calcule a apuração antes de transmitir, ou force assumindo o risco."
                    ),
                    "previa": previa,
                })
            if abs(float(div)) > self.TOLERANCIA_DIVERGENCIA:
                raise HTTPException(status_code=409, detail={
                    "erro": "divergencia_pac_rfb",
                    "mensagem": (
                        f"PAC e RFB divergem em R$ {float(div):.2f} "
                        f"(PAC R$ {previa.get('valor_devido_pac')} × RFB R$ {previa.get('valor_devido_rfb')}). "
                        "Revise a apuração antes de transmitir — ou force assumindo o risco."
                    ),
                    "divergencia": float(div),
                    "valor_devido_pac": previa.get("valor_devido_pac"),
                    "valor_devido_rfb": previa.get("valor_devido_rfb"),
                    "avisos": previa.get("avisos"),
                })
            # Serviço ignorado (Anexo I/II com receita de serviço) NÃO aparece na
            # divergência (motor e payload ignoram igual) → bloqueio próprio.
            srv = previa.get("servico_ignorado") or 0
            if float(srv) > self.TOLERANCIA_DIVERGENCIA:
                raise HTTPException(status_code=409, detail={
                    "erro": "servico_ignorado",
                    "mensagem": (
                        f"R$ {float(srv):.2f} de SERVIÇO não está sendo declarado — a empresa "
                        "está como Anexo I/II (comércio). Se ela presta serviço, ajuste o Anexo "
                        "(III/IV/V) no cadastro; se não, confirme. Revise antes de transmitir."
                    ),
                    "servico_ignorado": float(srv),
                    "avisos": previa.get("avisos"),
                })
        empresa = self.get_empresa_or_404(apur.empresa_id)
        interna, externa = self._receita_interna_externa(apur)
        receitas_anteriores = self._receitas_brutas_anteriores(apur.empresa_id, apur.ano_mes)
        avisos: list[str] = []

        # SERVIÇO IGNORADO: empresa com receita de serviço mas cadastrada como
        # comércio/indústria (Anexo I/II) → motor e payload ignoram o serviço.
        # PAC × RFB até batem (ambos ignoram), mas o DAS pode estar SUBESTIMADO se
        # a empresa de fato presta serviço (caso AGIMED). A divergência não pega
        # isso → guarda própria.
        _anx = (empresa.anexo_simples or "").upper()
        _anx_serv = (empresa.anexo_servico or "").upper()
        _mista = _anx_serv in {"III", "IV", "V"}  # mista declara o serviço → não é "ignorado"
        _servico = self._buckets_from_flat(apur).get("SERVICO", 0.0) or 0.0
        servico_ignorado = _servico if (
            _servico > 0.005 and _anx not in {"III", "IV", "V"} and not _mista
        ) else 0.0
        if servico_ignorado > 0.005:
            avisos.append(
                f"🔴 R$ {servico_ignorado:.2f} de SERVIÇO NÃO está sendo declarado: a empresa "
                f"está como Anexo {_anx or '(não definido)'} (comércio/indústria), que ignora "
                "serviço. Se ela presta serviço, ajuste o Anexo (III/IV/V) no cadastro; se não, "
                "confirme que não é receita tributável. NÃO transmita até resolver."
            )

        def _chamar(estabelecimentos: list[dict] | None, atividades: list[dict] | None):
            return self.provider.pgdas_transmitir_declaracao(
                empresa.cnpj,
                ano_mes=apur.ano_mes,
                receita_bruta=float(apur.receita_bruta),
                receita_interna=interna,
                receita_externa=externa,
                receitas_brutas_anteriores=receitas_anteriores,
                indicador_transmissao=not dry_run,
                atividades=atividades,
                estabelecimentos=estabelecimentos,
            )

        # Empresa com filial → estabelecimentos[] (matriz + filiais). Sem filial →
        # None, e o caminho antigo (atividades achatadas da matriz). Sem regressão.
        estabs = self._estabelecimentos_payload(apur, empresa)
        atividades = None if estabs else self._atividades_segregadas(apur, empresa.anexo_simples, empresa.anexo_servico)

        def _soma_ativ(es: list[dict] | None, ats: list[dict] | None) -> float:
            fonte: list[dict] = []
            if es:
                for e in es:
                    fonte.extend(e.get("atividades") or [])
            elif ats:
                fonte = ats
            return round(sum(float(a.get("valorAtividade") or 0) for a in fonte), 2)

        # PRÉ-CHECK: a soma das atividades TEM que bater com a receita interna,
        # senão a RFB rejeita (MSG_ISN_021 / MSG_E0056). Cata ANTES de gastar
        # chamada Serpro e mostra os números exatos pra diagnosticar.
        _soma = _soma_ativ(estabs, atividades)
        if abs(_soma - round(interna, 2)) > 0.01:
            raise HTTPException(status_code=400, detail={
                "erro": "soma_atividades_diverge",
                "mensagem": (
                    f"Soma das atividades R$ {_soma:.2f} ≠ receita interna R$ {round(interna, 2):.2f} "
                    f"(diferença R$ {_soma - round(interna, 2):.2f}). Payload no diagnostico."
                ),
                "receita_interna": round(interna, 2),
                "receita_externa": round(externa, 2),
                "soma_atividades": _soma,
                "anexo": empresa.anexo_simples,
                "anexo_servico": empresa.anexo_servico,
                "estabelecimentos": estabs,
                "atividades": atividades,
            })
        try:
            payload = _chamar(estabs, atividades)
        except IntegraContadorError as exc:
            # A RFB exige TODOS os estabelecimentos ativos do Cadastro CNPJ
            # (MSG_ISN_018) e diz QUAIS faltam → adiciona zeradas e retenta 1×.
            faltantes = [
                c for c in self._parse_estab_faltantes(str(exc))
                if c != self._so_digitos(empresa.cnpj)
            ]
            if faltantes:
                estabs = self._estabelecimentos_payload(apur, empresa, extra_zero=faltantes)
                avisos.append(
                    "Filiais declaradas com receita ZERO porque o PAC não tem as "
                    f"notas delas: {', '.join(faltantes)}. ⚠️ Se essas filiais "
                    "faturam, o DAS está SUBESTIMADO — puxe as notas delas (robô "
                    "por filial) antes de transmitir de verdade."
                )
                try:
                    payload = _chamar(estabs, None)
                except IntegraContadorError as exc2:
                    if not dry_run:
                        apur.status = StatusApuracao.ERRO
                        self.db.commit()
                    raise HTTPException(status_code=502, detail=f"Integra Contador: {exc2}")
            else:
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

        # DIAGNÓSTICO do payload (pra caçar mismatch de soma — MSG_ISN_021/E0056).
        def _soma_ativ(es: list[dict] | None, ats: list[dict] | None) -> float:
            fonte: list[dict] = []
            if es:
                for e in es:
                    fonte.extend(e.get("atividades") or [])
            elif ats:
                fonte = ats
            return round(sum(float(a.get("valorAtividade") or 0) for a in fonte), 2)

        return {
            "dry_run": dry_run,
            "valor_devido_rfb": valor_rfb,
            "valores_rfb": valores_rfb,
            "valor_devido_pac": valor_pac,
            "divergencia": divergencia,
            "servico_ignorado": round(servico_ignorado, 2),
            "diagnostico_payload": {
                "receita_bruta": round(float(apur.receita_bruta), 2),
                "receita_interna": round(interna, 2),
                "receita_externa": round(externa, 2),
                "soma_atividades": _soma_ativ(estabs, atividades),
                "anexo": empresa.anexo_simples,
                "anexo_servico": empresa.anexo_servico,
                "estabelecimentos": estabs,
                "atividades": atividades,
            },
            "raw": dados,
            "apuracao_id": apur.id,
            "status": apur.status.value,
            "avisos": avisos,
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
