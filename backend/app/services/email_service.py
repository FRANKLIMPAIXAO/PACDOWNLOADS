"""Envio de e-mail transacional via Resend (https://resend.com).

O domínio pacgestao.com.br já está VERIFICADO no Resend (SPF/DKIM ok), então
manda de @pacgestao.com.br direto. Se RESEND_API_KEY estiver vazia, `enviar_email`
retorna (False, motivo) SEM levantar — o chamador decide o fallback (ex.: devolver
o link do convite pra colar manual). E-mail nunca pode derrubar o fluxo principal.
"""
from __future__ import annotations

import httpx

from app.config import get_settings

settings = get_settings()
RESEND_URL = "https://api.resend.com/emails"


def email_configurado() -> bool:
    return bool(settings.resend_api_key)


def enviar_email(to: str, assunto: str, html: str) -> tuple[bool, str]:
    """Manda um e-mail via Resend. Retorna (ok, detalhe). Nunca levanta."""
    if not settings.resend_api_key:
        return False, "RESEND_API_KEY não configurada"
    try:
        r = httpx.post(
            RESEND_URL,
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from,
                "to": [to],
                "subject": assunto,
                "html": html,
            },
            timeout=20,
        )
        if r.status_code in (200, 201):
            try:
                return True, (r.json().get("id") or "enviado")
            except Exception:
                return True, "enviado"
        return False, f"Resend {r.status_code}: {r.text[:300]}"
    except Exception as exc:  # rede/timeout — não propaga
        return False, f"falha ao chamar Resend: {exc}"


def html_convite_cliente(nome: str, empresa_nome: str, link: str) -> str:
    """Convite pro portal do cliente. Estilo inline (e-mail ignora <style>).
    Cores PAC: navy #16294d, laranja #ec8b1c."""
    nome_ex = (nome or "").split(" ")[0] or "Olá"
    return f"""\
<div style="background:#f4f6fb;padding:32px 0;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e6e9f0;">
    <div style="background:#16294d;padding:24px 28px;">
      <span style="color:#ffffff;font-size:20px;font-weight:700;">PAC</span>
      <span style="color:#ec8b1c;font-size:20px;font-weight:700;">gestão</span>
    </div>
    <div style="padding:28px;color:#1c2330;font-size:15px;line-height:1.6;">
      <p style="margin:0 0 14px;">{nome_ex}, tudo bem?</p>
      <p style="margin:0 0 14px;">
        Você foi convidado para acessar o <strong>Portal do Cliente</strong> da
        <strong>{empresa_nome}</strong> — onde ficam suas certidões, guias de imposto
        e documentos fiscais, num só lugar.
      </p>
      <p style="margin:0 0 22px;">Clique no botão abaixo para criar sua senha e entrar:</p>
      <p style="text-align:center;margin:0 0 22px;">
        <a href="{link}" style="background:#ec8b1c;color:#ffffff;text-decoration:none;
           padding:13px 28px;border-radius:10px;font-weight:700;display:inline-block;">
          Criar minha senha
        </a>
      </p>
      <p style="margin:0 0 6px;color:#6b7280;font-size:13px;">
        Se o botão não funcionar, copie e cole este link no navegador:
      </p>
      <p style="margin:0 0 18px;word-break:break-all;font-size:12px;">
        <a href="{link}" style="color:#16294d;">{link}</a>
      </p>
      <p style="margin:0;color:#6b7280;font-size:12px;">
        O link expira em 7 dias. Se você não esperava este convite, pode ignorar este e-mail.
      </p>
    </div>
    <div style="background:#f4f6fb;padding:14px 28px;color:#9aa3b2;font-size:11px;text-align:center;">
      PAC Gestão · pacgestao.com.br
    </div>
  </div>
</div>"""
