"""Cliente do PacChat — a conversa com a PAC vive no backend do PacChat (Supabase
Edge Function), NÃO no PacGestão. Este serviço é a PONTE: o portal do cliente
chama o PacGestão (autenticado, escopado pela empresa do token), o PacGestão
resolve o CNPJ e fala com o PacChat usando o X-PAC-Token.

SEGURANÇA: o token (o MESMO das admissões) SÓ existe no backend — nunca vai pro
navegador. Todo request é escopado pelo CNPJ do cliente logado (derivado do
empresa_id do token, nunca do input), então um cliente não lê a conversa de outro.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("pac.pacchat")


class PacChatError(Exception):
    """Falha ao falar com o PacChat (config ausente, rede, HTTP não-2xx)."""


def _map_autor(autor_tipo: str | None) -> str:
    """PacChat usa 'interno' (PAC) / 'cliente'. No portal, 'interno' aparece como
    'escritorio' (bolha à esquerda) e 'cliente' como as bolhas do próprio cliente."""
    return "escritorio" if autor_tipo == "interno" else "cliente"


def map_mensagem(m: dict) -> dict:
    """Mensagem do PacChat → formato do ChatThread do portal. Inclui mídia
    (anexo/áudio): `tipo` (texto/imagem/video/audio/documento) + `midia_url`
    (URL pública pronta) + `midia_nome`."""
    return {
        "id": m.get("id"),
        "autor": _map_autor(m.get("autor_tipo")),
        "autor_nome": m.get("autor_nome"),
        "corpo": m.get("corpo") or "",
        "tipo": m.get("tipo") or "texto",
        "midia_url": m.get("midia_url"),
        "midia_nome": m.get("midia_nome"),
        "created_at": m.get("created_date"),
    }


class PacChatService:
    def __init__(self) -> None:
        s = get_settings()
        self.url = (s.pacchat_api_url or "").rstrip("/")
        # Reaproveita o token das admissões (mesmo X-PAC-Token, conforme o spec).
        self.token = s.pac_tarefas_webhook_token or ""

    @property
    def configurado(self) -> bool:
        return bool(self.url and self.token)

    def _call(self, acao: str, cnpj: str, **extra) -> dict:
        if not self.configurado:
            raise PacChatError(
                "PacChat não configurado (defina PAC_TAREFAS_WEBHOOK_TOKEN e PACCHAT_API_URL)."
            )
        body = {"acao": acao, "cnpj": cnpj, **{k: v for k, v in extra.items() if v is not None}}
        try:
            r = httpx.post(
                self.url,
                json=body,
                headers={"X-PAC-Token": self.token, "Content-Type": "application/json"},
                timeout=20,
            )
        except httpx.HTTPError as exc:
            # NUNCA logar o corpo/token — só a ação e o erro de transporte.
            logger.warning("PacChat %s falhou (rede): %s", acao, exc)
            raise PacChatError(f"Não foi possível falar com o PacChat: {exc}") from exc
        if r.status_code >= 400:
            logger.warning("PacChat %s HTTP %s", acao, r.status_code)
            raise PacChatError(f"PacChat respondeu {r.status_code}.")
        try:
            return r.json()
        except ValueError as exc:
            raise PacChatError("Resposta inválida do PacChat.") from exc

    # --- Ações (conforme o spec do PacChat) ---
    def conversas(self, cnpj: str) -> dict:
        return self._call("conversas", cnpj)

    def mensagens(self, cnpj: str, conversa_id: str | None = None, desde: str | None = None) -> dict:
        return self._call("mensagens", cnpj, conversa_id=conversa_id, desde=desde)

    def enviar(
        self,
        cnpj: str,
        texto: str | None = None,
        autor_nome: str | None = None,
        conversa_id: str | None = None,
        arquivo_base64: str | None = None,
        nome_arquivo: str | None = None,
        mimetype: str | None = None,
    ) -> dict:
        """Envia texto e/ou anexo. Pra mídia, manda o arquivo em base64 (o PacChat
        sobe pro Storage e devolve a midia_url). `_call` descarta os None, então
        mensagem só-texto vai sem os campos de mídia e vice-versa."""
        return self._call(
            "enviar", cnpj,
            texto=texto, autor_nome=autor_nome, conversa_id=conversa_id,
            arquivo_base64=arquivo_base64, nome_arquivo=nome_arquivo, mimetype=mimetype,
        )

    def marcar_lido(self, cnpj: str, conversa_id: str | None = None) -> dict:
        return self._call("marcar_lido", cnpj, conversa_id=conversa_id)

    # --- Ligação de voz (WebRTC) — o PacChat faz a sinalização; o PacGestão só
    #     proxia (o X-PAC-Token nunca vai pro navegador). ---
    def chamada_pendente(self, cnpj: str) -> dict:
        return self._call("chamada_pendente", cnpj)

    def chamada_iniciar(self, cnpj: str, offer: dict) -> dict:
        """CLIENTE inicia a chamada: publica o offer; o PacChat cria a chamada e
        faz a tela da equipe tocar. Retorna {chamada_id}. (Depende do PacChat
        expor a ação 'chamada_iniciar'.)"""
        return self._call("chamada_iniciar", cnpj, offer=offer)

    def chamada_responder(self, cnpj: str, chamada_id: str, aceitar: bool) -> dict:
        return self._call("chamada_responder", cnpj, chamada_id=chamada_id, aceitar=aceitar)

    def chamada_sinal(self, cnpj: str, chamada_id: str, tipo: str, payload: dict | None = None) -> dict:
        return self._call("chamada_sinal", cnpj, chamada_id=chamada_id, tipo=tipo, payload=payload)

    def chamada_sinais(self, cnpj: str, chamada_id: str, desde_seq: int = 0) -> dict:
        return self._call("chamada_sinais", cnpj, chamada_id=chamada_id, desde_seq=desde_seq)
