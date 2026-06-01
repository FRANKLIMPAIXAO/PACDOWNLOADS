"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError } from "../lib/api";
import { AlertasResposta, listarAlertas } from "../lib/agenda";

export function AlertasCard() {
  const [data, setData] = useState<AlertasResposta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarAlertas()
      .then(setData)
      .catch((err) => {
        if (err instanceof ApiError) setError(err.message);
        else setError("Falha ao carregar alertas.");
      });
  }, []);

  return (
    <section className="panel info-card">
      <header className="page-header" style={{ alignItems: "center" }}>
        <h3>Alertas</h3>
        {data ? (
          <div className="page-actions">
            {data.cnds_vencidas > 0 ? (
              <span className="pill pill-err">{data.cnds_vencidas} CND vencida(s)</span>
            ) : null}
            {data.cnds_a_vencer > 0 ? (
              <span className="pill pill-warn">{data.cnds_a_vencer} a vencer</span>
            ) : null}
            {data.mensagens_nao_lidas > 0 ? (
              <span className="pill pill-info">{data.mensagens_nao_lidas} eCAC</span>
            ) : null}
          </div>
        ) : null}
      </header>

      {error ? <p className="toast toast-error">{error}</p> : null}

      {!data ? (
        <p className="muted">Carregando...</p>
      ) : data.itens.length === 0 ? (
        <p className="muted">
          Tudo em ordem. Nenhum alerta no momento.
        </p>
      ) : (
        <div className="alert-list">
          {data.itens.map((a, i) => {
            const sevClass = `alert-item--${a.severidade}`;
            return (
              <div key={`${a.tipo}-${i}`} className={`alert-item ${sevClass}`}>
                <span className="alert-item-icon" />
                <div className="alert-item-body">
                  {a.empresa_id ? (
                    <Link href={`/empresas/${a.empresa_id}`} className="row-link" style={{ display: "block" }}>
                      <strong>{a.titulo}</strong>
                    </Link>
                  ) : (
                    <strong>{a.titulo}</strong>
                  )}
                  <small>{a.descricao}</small>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
