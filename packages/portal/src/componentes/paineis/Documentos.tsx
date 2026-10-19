"use client";

/**
 * Botão "Documentos" de uma publicação do PNCP: ao abrir, lista os arquivos publicados (edital, aviso,
 * contrato, aditivos) com o link de download na fonte. A lista é pedida à API do PNCP só quando aberta.
 */

import { useEffect, useState } from "react";
import { carregarDocumentos, type DocumentoPncp, lerChave } from "@/lib/documentos";
import { dataCurta } from "@/lib/paineis";

/** Fechado, buscando no PNCP, a lista pronta ou a falha da busca. */
type Estado = { fase: "fechado" } | { fase: "carregando" } | { fase: "pronto"; docs: DocumentoPncp[] } | { fase: "erro" };

/** Documentos de uma publicação, recolhidos até a pessoa abrir; nada aparece se a chave não é do PNCP. */
export function Documentos({ chave, link }: { chave: string; link: string | null }) {
  const [estado, setEstado] = useState<Estado>({ fase: "fechado" });
  const aberto = estado.fase !== "fechado";

  useEffect(() => {
    if (estado.fase !== "carregando") return;
    const c = new AbortController();
    carregarDocumentos(chave, c.signal)
      .then((docs) => setEstado({ fase: "pronto", docs }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setEstado({ fase: "erro" });
      });
    return () => c.abort();
  }, [estado.fase, chave]);

  if (!lerChave(chave)) return null;
  return (
    <span className="documentos">
      {" · "}
      <button type="button" className="botao-link" aria-expanded={aberto}
              onClick={() => setEstado(aberto ? { fase: "fechado" } : { fase: "carregando" })}>
        {aberto ? "fechar documentos" : "documentos"}
      </button>
      {estado.fase === "carregando" && <span className="documentos-lista busca-detalhe">Buscando no PNCP…</span>}
      {estado.fase === "erro" && (
        <span className="documentos-lista busca-detalhe">
          O PNCP não respondeu agora.{" "}
          {link && (
            <a href={link} target="_blank" rel="noreferrer">
              Ver a publicação
            </a>
          )}
        </span>
      )}
      {estado.fase === "pronto" && (
        <ul className="documentos-lista">
          {estado.docs.length === 0 && <li className="busca-detalhe">Nenhum documento anexado a esta publicação.</li>}
          {estado.docs.map((d) => (
            <li key={d.url}>
              <a href={d.url} target="_blank" rel="noreferrer" download>
                ⤓ {d.titulo}
              </a>
              <span className="busca-detalhe">
                {d.tipo ? ` · ${d.tipo}` : ""}
                {d.publicado_em ? ` · publicado em ${dataCurta(d.publicado_em)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}
