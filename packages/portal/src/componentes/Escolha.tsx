"use client";

/**
 * Caixa de escolha com busca, no lugar dos `<select>` do portal: mostra a opção escolhida; ao clicar (ou
 * focar e apertar seta para baixo) abre a lista inteira; ao escrever, a lista fica só com o que casa. Setas
 * para mover, Enter para escolher, Esc para fechar sem mudar. Segue o padrão ARIA de combobox com listbox.
 */

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { filtrarOpcoes, type Opcao } from "@/lib/escolha";

/** Caixa de escolha com busca; `onEscolher` recebe o `valor` da opção. */
export function Escolha({
  rotulo,
  opcoes,
  valor,
  onEscolher,
  className,
  vazio = "Nada encontrado.",
}: {
  rotulo: string;
  opcoes: readonly Opcao[];
  valor: string | null;
  onEscolher: (valor: string) => void;
  className?: string;
  vazio?: string;
}) {
  const id = useId();
  const [aberta, setAberta] = useState(false);
  const [termo, setTermo] = useState<string | null>(null);   // null: mostra a opção escolhida
  const [indice, setIndice] = useState(0);
  const caixa = useRef<HTMLDivElement>(null);
  const lista = useRef<HTMLUListElement>(null);
  const atual = opcoes.find((o) => o.valor === valor) ?? null;
  const achadas = useMemo(() => filtrarOpcoes(opcoes, termo ?? ""), [opcoes, termo]);

  useEffect(() => {
    const fora = (e: PointerEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) fechar();
    };
    document.addEventListener("pointerdown", fora);
    return () => document.removeEventListener("pointerdown", fora);
  }, []);

  useEffect(() => {
    if (!aberta) return;
    lista.current?.querySelector<HTMLElement>(`[data-indice="${indice}"]`)?.scrollIntoView({ block: "nearest" });
  }, [aberta, indice]);

  function fechar() {
    setAberta(false);
    setTermo(null);
  }

  function abrir() {
    const i = achadas.findIndex((o) => o.valor === valor);
    setIndice(i >= 0 ? i : 0);
    setAberta(true);
  }

  function escolher(o: Opcao | undefined) {
    if (!o) return;
    onEscolher(o.valor);
    fechar();
  }

  let grupoAnterior: string | undefined;
  return (
    <div className={`escolha ${className ?? ""}`} ref={caixa}>
      <input
        className="seletor escolha-campo"
        role="combobox"
        aria-label={rotulo}
        aria-autocomplete="list"
        aria-expanded={aberta}
        aria-controls={`${id}-lista`}
        aria-activedescendant={aberta && achadas[indice] ? `${id}-${indice}` : undefined}
        value={termo ?? atual?.rotulo ?? ""}
        placeholder={atual ? atual.rotulo : rotulo}
        title={atual?.rotulo}
        onFocus={(e) => e.currentTarget.select()}
        onClick={() => !aberta && abrir()}
        onChange={(e) => {
          setTermo(e.target.value);
          setIndice(0);
          setAberta(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            if (aberta) e.preventDefault();
            fechar();
          } else if (e.key === "ArrowDown") {
            e.preventDefault();
            if (!aberta) abrir();
            else setIndice((i) => Math.min(i + 1, achadas.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setIndice((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter" && aberta) {
            e.preventDefault();
            escolher(achadas[indice]);
          } else if (e.key === "Tab") fechar();
        }}
      />
      <span className="escolha-seta" aria-hidden="true">▾</span>
      {aberta && (
        <ul id={`${id}-lista`} role="listbox" aria-label={rotulo} className="busca-ente-lista escolha-lista" ref={lista}>
          {achadas.length === 0 && <li className="busca-vazio">{vazio}</li>}
          {achadas.map((o, i) => {
            const cabecalho = o.grupo && o.grupo !== grupoAnterior ? o.grupo : null;
            grupoAnterior = o.grupo;
            return (
              <li key={o.valor} role="presentation">
                {cabecalho && <div className="escolha-grupo" role="presentation">{cabecalho}</div>}
                <button
                  id={`${id}-${i}`}
                  data-indice={i}
                  type="button"
                  role="option"
                  tabIndex={-1}
                  aria-selected={i === indice}
                  className={o.valor === valor ? "escolhida" : undefined}
                  onMouseEnter={() => setIndice(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => escolher(o)}
                >
                  <span>{o.rotulo}</span>
                  {o.detalhe && <span className="busca-detalhe">{o.detalhe}</span>}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
