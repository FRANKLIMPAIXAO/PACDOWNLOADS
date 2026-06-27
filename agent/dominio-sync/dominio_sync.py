"""Agente Domínio-Sync — baixa os XMLs do PAC pra uma pasta que o Domínio monitora.

PONTE nuvem → local, SEM clique humano:

    PAC (nuvem) ──API──> este agente (seu servidor) ──grava──> pasta OneDrive
                                                                     │
                                              OneDrive espelha ──────┘
                                                                     ▼
                                          máquina do Domínio (pasta monitorada)
                                          → Domínio importa, roteando pelo CNPJ

Como funciona:
- INCREMENTAL: pega só os documentos NOVOS desde a última rodada (cursor por id).
- RESCAN: além disso, varre os últimos N dias pra pegar a RECEBIDA que entrou
  como "resumo" (sem XML) e só virou XML completo depois da manifestação.
- DEDUP por EXISTÊNCIA DO ARQUIVO: nunca regrava um XML que já está na pasta.
  (E o próprio Domínio deduplica por chave na importação — reenvio é inofensivo.)
- ESCRITA ATÔMICA: grava num .tmp e renomeia, pra o monitor do Domínio nunca
  pegar arquivo pela metade.

Agende no Agendador de Tarefas do Windows (ex.: a cada 1–2h). Config no
`config.env` ao lado deste arquivo (copie de `config.example.env`).

Uso:
    python dominio_sync.py                 # roda incremental + rescan
    python dominio_sync.py --rescan-dias 30
    python dominio_sync.py --dry-run       # mostra o que faria, sem gravar
    python dominio_sync.py --reset         # zera o cursor (re-baixa tudo)
    python dominio_sync.py --so-incremental
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

AQUI = Path(__file__).resolve().parent
ESTADO_PATH = AQUI / "estado.json"
LOG_PATH = AQUI / "logs" / "dominio_sync.log"

logger = logging.getLogger("dominio_sync")


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def _carregar_env() -> None:
    """Lê config.env (KEY=VALUE) pro os.environ, sem depender de python-dotenv.
    Variáveis já setadas no ambiente têm prioridade (não sobrescreve)."""
    cfg = AQUI / "config.env"
    if not cfg.is_file():
        return
    for linha in cfg.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        chave, valor = chave.strip(), valor.strip().strip('"').strip("'")
        if chave and chave not in os.environ:
            os.environ[chave] = valor


class Config:
    def __init__(self) -> None:
        self.base_url = os.environ.get("PAC_BASE_URL", "").rstrip("/")
        self.email = os.environ.get("PAC_EMAIL", "")
        self.password = os.environ.get("PAC_PASSWORD", "")
        self.pasta_base = Path(os.environ.get("PASTA_BASE", "")).expanduser()
        self.tipos = os.environ.get("TIPOS", "NFE,CTE")
        self.dias_rescan = int(os.environ.get("DIAS_RESCAN", "15"))
        # COMPETENCIA=AAAA-MM define o mês desejado e deriva data_min/data_max.
        # ESSENCIAL: sem janela a 1ª carga puxaria TODO o histórico (100k+ XMLs).
        self.competencia = os.environ.get("COMPETENCIA", "").strip()
        self.data_min = os.environ.get("DATA_MIN", "").strip()  # override cru
        self.data_max = os.environ.get("DATA_MAX", "").strip()  # override cru
        if self.competencia:
            import calendar
            try:
                ano, mes = (int(x) for x in self.competencia.split("-"))
                self.data_min = self.data_min or f"{ano:04d}-{mes:02d}-01"
                self.data_max = self.data_max or f"{ano:04d}-{mes:02d}-{calendar.monthrange(ano, mes)[1]:02d}"
            except (ValueError, TypeError):
                raise SystemExit(f"COMPETENCIA inválida (use AAAA-MM): {self.competencia!r}")
        # MODELOS=55 = só Nota Fiscal (exclui cupom NFC-e mod 65). Vazio = todos.
        self.modelos = os.environ.get("MODELOS", "").strip()
        # CNPJs (14 díg, csv) a IGNORAR — empresas de altíssimo volume tratadas à parte.
        self.excluir_cnpjs = os.environ.get("EXCLUIR_CNPJS", "").strip()
        self.layout = os.environ.get("LAYOUT", "arvore").lower()  # arvore | plano
        self.incluir_canceladas = os.environ.get("INCLUIR_CANCELADAS", "true").lower() in ("1", "true", "sim", "yes")
        self.limite_pagina = int(os.environ.get("LIMITE_PAGINA", "2000"))
        self.timeout = float(os.environ.get("TIMEOUT", "60"))

    def validar(self) -> None:
        faltando = [
            nome for nome, val in (
                ("PAC_BASE_URL", self.base_url),
                ("PAC_EMAIL", self.email),
                ("PAC_PASSWORD", self.password),
                ("PASTA_BASE", str(self.pasta_base) if self.pasta_base != Path("") else ""),
            ) if not val
        ]
        if faltando:
            raise SystemExit(
                f"Config faltando: {', '.join(faltando)}. "
                f"Edite {AQUI / 'config.env'} (copie de config.example.env)."
            )
        if self.layout not in ("arvore", "plano"):
            raise SystemExit("LAYOUT deve ser 'arvore' ou 'plano'.")


# --------------------------------------------------------------------------- #
# Cliente PAC (login + manifesto + download)
# --------------------------------------------------------------------------- #
class PacSyncClient:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._c = httpx.Client(base_url=cfg.base_url, timeout=cfg.timeout, follow_redirects=True)

    def _retry(self, fn, *, tentativas: int = 3, espera: float = 3.0) -> httpx.Response:
        """Repete em falha de REDE (timeout/conexão) ou HTTP 5xx — transitórios.
        4xx não repete (não adianta). Backoff linear."""
        ult: Exception | None = None
        for i in range(1, tentativas + 1):
            try:
                r = fn()
                r.raise_for_status()
                return r
            except httpx.TransportError as exc:  # cobre timeout, connect, read
                ult = exc
                logger.warning("tentativa %s/%s falhou (rede): %s", i, tentativas, exc)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500:
                    raise
                ult = exc
                logger.warning("tentativa %s/%s falhou (HTTP %s)", i, tentativas, exc.response.status_code)
            if i < tentativas:
                time.sleep(espera * i)
        assert ult is not None
        raise ult

    def login(self) -> None:
        r = self._retry(lambda: self._c.post(
            "/api/v1/auth/login", json={"email": self.cfg.email, "password": self.cfg.password},
        ))
        token = r.json()["access_token"]
        self._c.headers["Authorization"] = f"Bearer {token}"
        logger.info("Autenticado no PAC como %s", self.cfg.email)

    def manifesto(self, *, desde_id: int = 0, dias: int = 0) -> dict:
        params: dict[str, object] = {
            "desde_id": desde_id,
            "dias": dias,
            "tipos": self.cfg.tipos,
            "limite": self.cfg.limite_pagina,
        }
        if self.cfg.data_min:
            params["data_min"] = self.cfg.data_min
        if self.cfg.data_max:
            params["data_max"] = self.cfg.data_max
        if self.cfg.modelos:
            params["modelos"] = self.cfg.modelos
        if self.cfg.excluir_cnpjs:
            params["cnpjs_excluir"] = self.cfg.excluir_cnpjs
        r = self._retry(lambda: self._c.get("/api/v1/documentos/sync-manifest", params=params))
        return r.json()

    def baixar_xml(self, doc_id: int) -> bytes:
        r = self._retry(lambda: self._c.get(f"/api/v1/documentos/{doc_id}/download"))
        return r.content

    def close(self) -> None:
        self._c.close()


# --------------------------------------------------------------------------- #
# Estado (cursor)
# --------------------------------------------------------------------------- #
def ler_estado() -> dict:
    if ESTADO_PATH.is_file():
        try:
            return json.loads(ESTADO_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("estado.json ilegível — recomeçando do zero")
    return {"ultimo_id": 0}


def salvar_estado(estado: dict) -> None:
    tmp = ESTADO_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ESTADO_PATH)


# --------------------------------------------------------------------------- #
# Gravação na pasta
# --------------------------------------------------------------------------- #
def caminho_destino(cfg: Config, doc: dict) -> Path:
    """Monta o caminho do XML na pasta. `arvore`: <base>/<CNPJ>/<AAAA-MM>/<TIPO>/<chave>.xml.
    `plano`: <base>/<CNPJ>_<TIPO>_<chave>.xml (use se o Domínio não varre subpastas)."""
    cnpj = (doc.get("cnpj_empresa") or "sem-cnpj").strip()
    chave = (doc.get("chave") or f"doc{doc['id']}").strip()
    tipo = doc.get("tipo", "DOC")
    if cfg.layout == "plano":
        return cfg.pasta_base / f"{cnpj}_{tipo}_{chave}.xml"
    comp = doc.get("competencia") or "sem-data"
    return cfg.pasta_base / cnpj / comp / tipo / f"{chave}.xml"


def gravar_atomico(destino: Path, conteudo: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_bytes(conteudo)
    os.replace(tmp, destino)  # rename atômico — o monitor do Domínio só vê o final


# --------------------------------------------------------------------------- #
# Sincronização
# --------------------------------------------------------------------------- #
def _processar_lote(
    cli: PacSyncClient, cfg: Config, docs: list[dict], stats: dict, *, dry_run: bool
) -> None:
    for doc in docs:
        if doc.get("cancelada") and not cfg.incluir_canceladas:
            stats["puladas_canceladas"] += 1
            continue
        destino = caminho_destino(cfg, doc)
        if destino.exists():
            stats["ja_existiam"] += 1
            continue
        if dry_run:
            logger.info("[dry-run] baixaria %s", destino)
            stats["baixados"] += 1
            continue
        try:
            conteudo = cli.baixar_xml(doc["id"])
            if not conteudo:
                stats["erros"] += 1
                logger.warning("doc %s veio vazio", doc["id"])
                continue
            gravar_atomico(destino, conteudo)
            stats["baixados"] += 1
        except httpx.HTTPError as exc:
            stats["erros"] += 1
            logger.warning("falha ao baixar doc %s: %s", doc["id"], exc)


def sincronizar(cfg: Config, *, dry_run: bool, so_incremental: bool, rescan_dias: int | None) -> dict:
    cli = PacSyncClient(cfg)
    stats = {"baixados": 0, "ja_existiam": 0, "erros": 0, "puladas_canceladas": 0}
    try:
        cli.login()
        estado = ler_estado()
        cursor = int(estado.get("ultimo_id", 0))

        # 1) INCREMENTAL — pagina pelo cursor até não ter mais.
        logger.info("Incremental a partir do id %s (tipos=%s)", cursor, cfg.tipos)
        while True:
            m = cli.manifesto(desde_id=cursor, dias=0)
            docs = m.get("documentos", [])
            if docs:
                _processar_lote(cli, cfg, docs, stats, dry_run=dry_run)
            novo_cursor = int(m.get("proximo_desde_id", cursor))
            if not dry_run and novo_cursor > cursor:
                cursor = novo_cursor
                estado["ultimo_id"] = cursor
                salvar_estado(estado)  # salva a cada página — resiliente a queda
            if not m.get("tem_mais"):
                break

        # 2) RESCAN — pega manifestação tardia de RECEBIDA (id antigo, XML novo).
        dias = rescan_dias if rescan_dias is not None else cfg.dias_rescan
        if not so_incremental and dias > 0:
            logger.info("Rescan dos últimos %s dias (manifestação tardia)", dias)
            m = cli.manifesto(desde_id=0, dias=dias)
            docs = m.get("documentos", [])
            _processar_lote(cli, cfg, docs, stats, dry_run=dry_run)
            if m.get("tem_mais"):
                logger.warning(
                    "Rescan truncado em %s docs (LIMITE_PAGINA). Reduza DIAS_RESCAN "
                    "ou aumente o limite se faltar nota.", cfg.limite_pagina,
                )

        if not dry_run:
            estado["ultima_execucao"] = datetime.now(timezone.utc).isoformat()
            estado["ultimas_stats"] = stats
            salvar_estado(estado)
        return stats
    finally:
        cli.close()


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _setup_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
    )


def main() -> int:
    # Blindagem Windows: console em cp1252 quebra ao imprimir acento. Força utf-8.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Agente Domínio-Sync (PAC → pasta → Domínio)")
    ap.add_argument("--dry-run", action="store_true", help="não grava nada, só mostra")
    ap.add_argument("--reset", action="store_true", help="zera o cursor (re-baixa tudo)")
    ap.add_argument("--so-incremental", action="store_true", help="pula o rescan")
    ap.add_argument("--rescan-dias", type=int, default=None, help="sobrescreve DIAS_RESCAN")
    args = ap.parse_args()

    _setup_logging()
    _carregar_env()
    cfg = Config()
    cfg.validar()

    if args.reset and ESTADO_PATH.exists():
        ESTADO_PATH.unlink()
        logger.info("Cursor zerado (--reset).")

    logger.info(
        "Pasta: %s | tipos=%s | janela=%s..%s | modelos=%s | excluir=%s | layout=%s | rescan=%sd",
        cfg.pasta_base, cfg.tipos, cfg.data_min or "(inicio)", cfg.data_max or "(hoje)",
        cfg.modelos or "(todos)", cfg.excluir_cnpjs or "(nenhum)", cfg.layout, cfg.dias_rescan,
    )
    try:
        stats = sincronizar(
            cfg, dry_run=args.dry_run, so_incremental=args.so_incremental, rescan_dias=args.rescan_dias,
        )
    except httpx.HTTPStatusError as exc:
        logger.error("Erro HTTP do PAC: %s — %s", exc.response.status_code, exc.response.text[:300])
        return 2
    except httpx.HTTPError as exc:
        logger.error("Falha de rede com o PAC: %s", exc)
        return 2

    logger.info(
        "FIM. baixados=%(baixados)s já_existiam=%(ja_existiam)s "
        "canceladas_puladas=%(puladas_canceladas)s erros=%(erros)s", stats,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
