"""Painéis de contratações e de conformidade fiscal do portal (ADR-028).

O portal mostra, para cada ente federativo (União, estados, Distrito Federal e municípios), dois panoramas
feitos só de fatos publicados pela própria administração:

- **Contratações** (UC-01 e UC-02): o que o ente publicou no PNCP — processos de contratação por mês e por
  modalidade, contratos assinados, os órgãos que mais publicaram, os fornecedores pessoa jurídica com maior
  valor contratado e as publicações mais recentes, cada uma com o link para a página dela no PNCP. Pessoa
  física nunca aparece por nome nem documento: entra só numa soma anônima (RNF-19 e RNF-20).
- **Conformidade** (UC-07, RF-CF-01 e RF-CF-02): se os relatórios da Lei de Responsabilidade Fiscal (contas
  anuais, RREO e RGF) constam do extrato de entregas do Tesouro e em que data, contra o prazo legal; quando a
  coleta falha ou o prazo ainda não venceu, o resultado é indeterminado e nada é atribuído ao ente (RF-CF-07).

Nenhum dos dois publica indício nem ordena entes por risco (PUB-07): as regras de sinalização seguem em
calibração e revisão (DOC-07, DOC-08), e o painel só reúne e soma o que as fontes publicaram.

Módulos:

- ``comum``: leitura e gravação de JSON (comprimido ou não), códigos dos entes, modalidades do PNCP e links;
- ``cadastro``: nomes, UF e população dos entes, do cadastro do SICONFI;
- ``dia``: a coleta de um dia do PNCP, reduzida ao que os painéis usam (o estado guardado entre execuções);
- ``contratacoes``: soma os dias em arquivos por ente, o panorama e o índice de busca;
- ``conformidade``: coleta o extrato de entregas por UF e avalia cada obrigação na data da publicação;
- ``site``: grava o diretório publicado (GitHub Pages);
- ``cli``: ``lumen painel …``.
"""

VERSAO_PAINEL = 1
