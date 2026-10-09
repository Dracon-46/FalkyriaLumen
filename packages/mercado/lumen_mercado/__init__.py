"""Referência de mercado fora do governo para os preços pagos pelos entes (regra A-05, ADR-027).

A família A do DOC-07 compara o preço de um item com o que outros órgãos pagaram (A-01) ou com tabelas
oficiais (A-02). As duas referências nascem do próprio poder público: se o mercado inteiro de compras
públicas paga caro por um item, a mediana entre órgãos também fica cara e nada destoa. Este pacote traz uma
referência independente do comprador público:

- ``anp``: preço de bomba dos combustíveis, pesquisado pela ANP posto a posto, toda semana, em todo o país
  (dado aberto oficial, em arquivos semestrais desde 2006);
- ``varejo``: ofertas do varejo online obtidas pela API oficial de cada loja (hoje, a do Mercado Livre);
- ``especificacao``: reconhece, pela descrição do item, o que é comparável e com qual referência;
- ``comparacao``: a regra A-05, em modo silencioso — calcula a razão entre o preço pago e a mediana do
  mercado na mesma época e no mesmo lugar, e grava o resultado num relatório interno; nada é publicado
  antes da calibração (DOC-07, seção 1);
- ``relatorio``: o relatório em JSON Lines, CSV e um resumo em Markdown.

O preço acima da referência comparada é atividade para análise, nunca conclusão: há razões legítimas para
o governo pagar mais que a bomba ou a loja (entrega no local, prazo de pagamento, quantidade, garantia), e
o relatório mostra a referência inteira para quem for analisar.
"""

VERSAO_REGRA = "A-05/1"
