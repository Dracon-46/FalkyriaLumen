#!/usr/bin/env bash
# Dias do painel de contratações nos anexos de versões do GitHub (ADR-028, ADR-046).
#
# Um release aceita no máximo 1.000 anexos, e o histórico desde agosto de 2021 passa de 1.800 dias. Por isso
# cada ano fica numa versão própria, "painel-dias-AAAA". Os dias de 2026 guardados antes desta divisão
# continuam na versão "painel-estado" e são lidos junto (o nome do arquivo é o mesmo; o mais novo vale).
#
#   dias.sh marcar  <dir>            cria arquivos vazios com o nome de cada dia já guardado (para o "faltando")
#   dias.sh baixar  <dir>            baixa todos os dias guardados
#   dias.sh guardar <arquivo>...     envia cada dia para a versão do ano dele (cria a versão se faltar)
#
# Usa o gh já autenticado (GH_TOKEN) no repositório da execução.
set -euo pipefail

LEGADO="painel-estado"
NOTAS="Dias do painel de contratações do Lumen (ADR-028): um arquivo por dia do PNCP, de um ano. Gerado pelos fluxos paineis e paineis-carga; não é uma versão do software."

# A versão antiga primeiro: no "baixar", o dia que existe nas duas fica com o da versão do ano, mais novo
versoes() {
  echo "$LEGADO"
  gh release list --limit 200 --json tagName --jq '.[].tagName' | grep '^painel-dias-' | sort || true
}

case "${1:-}" in
  marcar)
    mkdir -p "$2"
    for v in $(versoes); do
      gh release view "$v" --json assets --jq '.assets[].name' 2>/dev/null | grep '^contratacoes-' | while read -r n; do : > "$2/$n"; done
    done
    ;;
  baixar)
    mkdir -p "$2"
    for v in $(versoes); do
      gh release download "$v" -p 'contratacoes-*.json.gz' -D "$2" --clobber 2>/dev/null || true
    done
    ;;
  guardar)
    shift
    for f in "$@"; do
      nome=$(basename "$f")
      ano=${nome:13:4}
      v="painel-dias-$ano"
      gh release view "$v" >/dev/null 2>&1 || gh release create "$v" --prerelease --title "Dias do painel, $ano" --notes "$NOTAS"
      gh release upload "$v" "$f" --clobber
    done
    ;;
  *)
    echo "uso: $0 marcar <dir> | baixar <dir> | guardar <arquivo>..." >&2
    exit 2
    ;;
esac
