"use client";

/**
 * Diálogo de busca de estado ou município. A filtragem é local (`buscar`),
 * sobre o cadastro que o painel baixa na primeira vez que a busca abre.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { buscar, type Achado } from "@/lib/busca";
import type { Municipio } from "@/lib/tipos";

/** Entrada da busca: visibilidade, cadastro e o que fazer ao fechar ou ao escolher um resultado. */
interface Props {
  aberta: boolean;
  /** Vazio enquanto o cadastro não chegou, ou quando o servidor não o tem. */
  municipios: Municipio[];
  onFechar: () => void;
  onEscolher: (achado: Achado) => void;
  /** O que a pessoa já escreveu no campo da página antes de a busca abrir. */
  termoInicial?: string;
}

/** Busca de estado ou município (Ctrl+K ou "/"). Setas escolhem, Enter abre, Esc fecha. */
export function Busca({ aberta, municipios, onFechar, onEscolher, termoInicial = "" }: Props) {
  const [termo, setTermo] = useState("");
  const [indice, setIndice] = useState(0);
  const campo = useRef<HTMLInputElement>(null);
  const achados = useMemo(() => buscar(termo, municipios), [termo, municipios]);

  useEffect(() => {
    if (aberta) {
      setTermo(termoInicial);
      setIndice(0);
      campo.current?.focus();
    }
  }, [aberta, termoInicial]);

  if (!aberta) return null;

  const escolher = (a: Achado | undefined) => {
    if (!a) return;
    onEscolher(a);
    onFechar();
  };

  return (
    <div
      className="busca-fundo"
      role="presentation"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onFechar();
      }}
    >
      <div className="busca" role="dialog" aria-modal="true" aria-label="Buscar estado ou município">
        <input
          ref={campo}
          value={termo}
          placeholder="Estado ou município"
          aria-label="Estado ou município"
          aria-controls="busca-resultados"
          aria-activedescendant={achados[indice] ? `busca-${indice}` : undefined}
          onChange={(e) => {
            setTermo(e.target.value);
            setIndice(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onFechar();
            else if (e.key === "ArrowDown") {
              e.preventDefault();
              setIndice((i) => Math.min(i + 1, achados.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setIndice((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") escolher(achados[indice]);
          }}
        />
        {termo && achados.length === 0 && (
          <div className="busca-vazio">
            Nada encontrado.
            {municipios.length === 0 && " O cadastro de municípios não está disponível neste servidor."}
          </div>
        )}
        {achados.length > 0 && (
          <ul id="busca-resultados" role="listbox" aria-label="Resultados">
            {achados.map((a, i) => (
              <li key={a.abrangencia}>
                <button
                  id={`busca-${i}`}
                  type="button"
                  role="option"
                  aria-selected={i === indice}
                  onPointerEnter={() => setIndice(i)}
                  onClick={() => escolher(a)}
                >
                  <span>{a.rotulo}</span>
                  <span className="busca-detalhe">{a.detalhe}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
