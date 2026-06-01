"""Service de alto nível para consultas Infosimples — provider + cache TTL.

Caller (CndRoboService, ParcelamentoPgfnService) usa ESTE service, não o
provider direto. Aqui acontece:
1. Lookup no cache (economiza pré-pago)
2. Se MISS → chama provider real
3. Salva resposta no cache com TTL dinâmico (baseado em situação da CND)

TTLs:
- CND VALIDA (validade > 30d) → 30 dias
- CND A_VENCER (validade <= 30d) → 7 dias
- CND VENCIDA → 1 dia
- PGFN parcelamentos → 7 dias (situação muda quando paga parcela)
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date
from typing import Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.providers.infosimples import (
    CndInfosimples,
    InfosimplesProvider,
)
from app.services import infosimples_cache as cache_helper


logger = logging.getLogger(__name__)


# FEDERAL_OFICIAL → Integra Contador (Serpro), mais barato.
# TRABALHISTA → cadastro manual (consulta rara, não compensa Infosimples).
TipoCndInfosimples = Literal["FGTS", "ESTADUAL"]


ENDPOINT_POR_TIPO_CND = {
    "FGTS": "/consultas/caixa/regularidade",
    # ESTADUAL é variável por UF — endpoint dinâmico `/consultas/sefaz/{uf}/certidao-debitos`
    # Cache key inclui a UF via payload pra não confundir GO vs SP da mesma empresa.
    "ESTADUAL": "/consultas/sefaz/estadual",  # placeholder — endpoint real montado em runtime
}


class InfosimplesService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.provider = InfosimplesProvider()
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # CND (qualquer tipo) — com cache TTL dinâmico
    # ------------------------------------------------------------------

    def cnd(
        self, *, cnpj: str, tipo: TipoCndInfosimples,
        uf: str | None = None, force: bool = False,
    ) -> tuple[CndInfosimples, bool]:
        """Consulta CND. Retorna (resultado, veio_do_cache).

        TTL escolhido baseado na situação: VALIDA=30d, A_VENCER=7d, VENCIDA=1d.
        Quando cache HIT, TTL não importa (resposta já cacheada com seu próprio).

        Args:
            cnpj: CNPJ com ou sem máscara
            tipo: tipo da CND
            uf: obrigatório se tipo='ESTADUAL' (2 letras). Cacheia separado
                por UF — uma empresa em GO ≠ a mesma em SP.
            force: bypassa cache (custa 1 consulta paga)
        """
        # Endpoint dinâmico pra ESTADUAL inclui UF; cache_key separa por UF.
        if tipo == "ESTADUAL":
            if not uf:
                raise ValueError("UF obrigatória pra CND ESTADUAL")
            endpoint = f"/consultas/sefaz/{uf.lower()}/certidao-debitos"
        else:
            endpoint = ENDPOINT_POR_TIPO_CND[tipo]

        def fetcher() -> CndInfosimples:
            if tipo == "FGTS":
                return self.provider.crf_fgts(cnpj)
            if tipo == "ESTADUAL":
                return self.provider.cnd_sefaz_estadual(cnpj, uf or "")
            raise ValueError(f"Tipo CND não suportado pelo Infosimples: {tipo}")

        # Serializer / deserializer pra dataclass
        def serializer(c: CndInfosimples) -> dict:
            d = asdict(c)
            # date → ISO string pra cabe no JSON
            d["data_emissao"] = c.data_emissao.isoformat() if c.data_emissao else None
            d["data_validade"] = c.data_validade.isoformat() if c.data_validade else None
            d["pdf_bytes"] = None  # nunca cacheia binário, baixa sob demanda
            return d

        def deserializer(d: dict) -> CndInfosimples:
            return CndInfosimples(
                cnpj=d["cnpj"],
                tipo=d["tipo"],
                numero=d.get("numero"),
                data_emissao=date.fromisoformat(d["data_emissao"]) if d.get("data_emissao") else None,
                data_validade=date.fromisoformat(d["data_validade"]) if d.get("data_validade") else None,
                situacao=d.get("situacao", "indisponivel"),
                pdf_url=d.get("pdf_url"),
                pdf_bytes=None,
                raw=d.get("raw") or {},
                custo_centavos=int(d.get("custo_centavos") or 0),
                billable=bool(d.get("billable", True)),
                mensagem=d.get("mensagem"),
            )

        # Primeira chamada usa TTL conservador. Após a chamada, ajustamos
        # baseado na situação retornada (re-salva com TTL correto).
        ttl_dias = self._settings.infosimples_cache_cnd_dias  # 30d default

        resultado, hit = cache_helper.get_or_call(
            self.db,
            cnpj=cnpj,
            endpoint=endpoint,
            fetcher=fetcher,
            ttl_dias=ttl_dias,
            serializer=serializer,
            deserializer=deserializer,
            force=force,
        )

        # Se foi MISS, re-salva com TTL baseado na situação real
        if not hit and resultado.data_validade:
            dias_pra_vencer = (resultado.data_validade - date.today()).days
            if dias_pra_vencer < 0:
                ttl_real = 1  # vencida — re-tenta amanhã
            elif dias_pra_vencer <= 30:
                ttl_real = 7  # a vencer — re-checa semanal
            else:
                ttl_real = 30  # válida — re-checa mensal
            if ttl_real != ttl_dias:
                cache_helper.set_cache(
                    self.db, cnpj=cnpj, endpoint=endpoint,
                    response=serializer(resultado),
                    ttl_dias=ttl_real,
                )
                logger.info(
                    "Ajustou TTL pra %dd baseado em validade %s (dias=%d)",
                    ttl_real, resultado.data_validade, dias_pra_vencer,
                )

        return resultado, hit

    # ------------------------------------------------------------------
    # PGFN parcelamentos
    # ------------------------------------------------------------------

    # PGFN parcelamentos: NÃO tem produto Infosimples. Cadastro manual via
    # ParcelamentoPgfnService — método sync_empresa fica deprecated e devolve
    # erro claro. Fontes futuras: parser SITFIS PDF, scraper REGULARIZE.

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------

    def invalidar_cache_empresa(self, cnpj: str) -> int:
        """Apaga TODO o cache Infosimples dessa empresa. Custa moeda na próxima."""
        return cache_helper.invalidar(self.db, cnpj=cnpj)
