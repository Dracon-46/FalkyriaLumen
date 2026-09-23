const L = require("./lib");
const { h1, h2, h3, p, bullet, numbered, table, callout, code, figure, pageBreak, spacer } = L;

const body = [];

body.push(h1("1. Convenções de nomenclatura"));
body.push(h2("1.1 Idioma do código"));
body.push(p("O domínio deste sistema é o direito administrativo brasileiro. Traduzir seus conceitos para " +
  "o inglês produz ambiguidade e perda de precisão: dispensa de licitação, empenho, liquidação, " +
  "inexigibilidade e amparo legal não têm equivalente exato, e qualquer tradução obriga o " +
  "desenvolvedor a fazer o caminho de volta mentalmente toda vez que lê o código."));
body.push(table(["Camada", "Idioma", "Justificativa"], [2800, 1800, 5000], [
  ["Entidades de domínio", "Português", "Termos jurídicos sem equivalente preciso em inglês"],
  ["Campos do esquema canônico", "Português", "Correspondência direta com a nomenclatura das fontes oficiais"],
  ["Regras de detecção", "Português", "Explicações públicas derivam diretamente dos nomes internos"],
  ["Infraestrutura e utilitários", "Inglês", "Convenção do ecossistema; sem carga de domínio"],
  ["Bibliotecas de terceiros", "Inglês", "Não se traduz o que não é nosso"],
]));
body.push(code([
  "# correto: o termo juridico preservado",
  "class ProcessoContratacao:",
  "    amparo_legal: AmparoLegal | None",
  "    modalidade: Modalidade",
  "",
  "    def eh_contratacao_direta(self) -> bool:",
  "        return self.modalidade in (Modalidade.DISPENSA, Modalidade.INEXIGIBILIDADE)",
  "",
  "# incorreto: traducao que perde precisao juridica",
  "class BiddingProcess:",
  "    legal_basis: str | None       # \"amparo legal\" nao e \"legal basis\"",
  "    mode: str                     # \"modalidade\" tem taxonomia legal fechada",
  "",
  "# infraestrutura permanece em ingles",
  "class S3ArtifactStore(ArtifactStore):",
  "    def put(self, key: str, payload: bytes) -> str: ...",
]));

body.push(h2("1.2 Regras gerais"));
body.push(table(["Elemento", "Convenção", "Exemplo"], [2400, 2600, 4600], [
  ["Módulo e arquivo Python", "snake_case", "processo_contratacao.py"],
  ["Classe", "PascalCase", "ProcessoContratacao"],
  ["Função e variável Python", "snake_case", "calcular_escore_robusto"],
  ["Constante", "UPPER_SNAKE_CASE", "LIMITE_DISPENSA_COMPRAS"],
  ["Arquivo TypeScript", "kebab-case", "indicio-controller.ts"],
  ["Função e variável TS", "camelCase", "buscarIndiciosPorEnte"],
  ["Tabela e coluna SQL", "snake_case singular", "processo_contratacao, valor_unitario"],
  ["Código de regra", "letra da família + sequencial", "B-01, D-04"],
  ["Especificação de fonte", "uf_ente_objeto", "sp_campinas_contratos.yaml"],
]));

body.push(h2("1.3 Valores legais nunca ficam no código"));
body.push(p("Limites de dispensa, percentuais de aditivo e prazos mínimos mudam por decreto. Fixá-los no " +
  "código significa que uma mudança normativa exige alteração de código, revisão e implantação — e, " +
  "pior, invalida silenciosamente a reprodução de análises de períodos anteriores."));
body.push(code([
  "# INCORRETO: valor fixo no codigo, sem vigencia",
  "if valor > 65492.11:",
  "    disparar_indicio()",
  "",
  "# CORRETO: parametro datado, consultado pela data do ato",
  "limite = parametros_legais.obter(",
  "    chave=\"dispensa.compras_servicos\",",
  "    vigente_em=processo.data_publicacao,",
  ")",
  "if processo.valor_estimado > limite.valor:",
  "    disparar_indicio(",
  "        referencia=limite,          # guarda valor, decreto e vigencia",
  "        observado=processo.valor_estimado,",
  "    )",
  "",
  "# parametros_legais.yaml",
  "# dispensa.compras_servicos:",
  "#   - valor: 65492.11",
  "#     vigente_de: 2026-01-01",
  "#     fundamento: \"Lei 14.133/2021, art. 75, II\"",
  "#     atualizado_por: \"Decreto 12.807/2025\"",
]));
body.push(callout("Por que isso é requisito e não preferência", [
  "Um indício calculado hoje sobre um contrato de 2024 precisa usar o limite vigente em 2024, não o de " +
  "hoje. Sem parâmetros datados, todo reprocessamento histórico produziria indícios incorretos, e o " +
  "princípio de reprodutibilidade do DOC-01 seria violado de forma invisível.",
], "red"));

body.push(pageBreak());
body.push(h1("2. Verificador de vocabulário controlado"));
body.push(p("Este é o componente que transforma a restrição editorial mais importante do projeto em " +
  "propriedade verificável do sistema, conforme a ADR-007. Ele roda na integração contínua e interrompe " +
  "o build quando encontra violação."));
body.push(code([
  "#!/usr/bin/env python3",
  "\"\"\"Verificador de vocabulario controlado (DOC-08, secao 3).",
  "",
  "Percorre todo texto destinado ao publico e falha quando encontra termo",
  "que impute conduta ilicita. Roda na integracao continua.",
  "\"\"\"",
  "import re, sys, unicodedata",
  "from pathlib import Path",
  "",
  "# Alvos: tudo que pode chegar aos olhos do publico.",
  "ALVOS = [",
  "    \"packages/portal/**/*.{tsx,ts}\",",
  "    \"packages/api/**/mensagens/*.ts\",",
  "    \"packages/deteccao/regras/**/*.py\",   # explicacao_publica",
  "    \"conteudo/**/*.md\",",
  "]",
  "",
  "PROIBIDOS = {",
  "    \"desvio\", \"desviou\", \"fraude\", \"fraudulento\", \"fraudar\",",
  "    \"superfaturamento\", \"superfaturado\", \"corrupcao\", \"corrupto\",",
  "    \"suspeito\", \"suspeita\", \"irregular\", \"irregularidade\",",
  "    \"ilegal\", \"ilicito\", \"crime\", \"criminoso\", \"culpado\",",
  "    \"propina\", \"lavagem\", \"esquema\", \"denuncia\", \"acusado\",",
  "}",
  "",
  "SUGESTOES = {",
  "    \"desvio\": \"valor em analise\",",
  "    \"fraude\": \"padrao atipico identificado\",",
  "    \"superfaturamento\": \"preco acima da referencia comparada\",",
  "    \"suspeito\": \"atividade para analise\",",
  "    \"irregularidade\": \"divergencia em relacao ao parametro\",",
  "}",
  "",
  "def normalizar(texto: str) -> str:",
  "    \"\"\"Remove acentos e caixa: 'Corrupção' e 'corrupcao' sao o mesmo termo.\"\"\"",
  "    sem_acento = unicodedata.normalize(\"NFKD\", texto)",
  "    sem_acento = \"\".join(c for c in sem_acento if not unicodedata.combining(c))",
  "    return sem_acento.lower()",
  "",
  "def verificar(caminho: Path) -> list[tuple[int, str, str]]:",
  "    achados = []",
  "    for n, linha in enumerate(caminho.read_text(encoding=\"utf-8\").splitlines(), 1):",
  "        if \"lumen:vocabulario-ok\" in linha:   # excecao justificada e revisada",
  "            continue",
  "        normalizada = normalizar(linha)",
  "        for termo in PROIBIDOS:",
  "            # \\b evita casar 'desvio' dentro de 'desvio_padrao' (termo estatistico)",
  "            if re.search(rf\"\\b{termo}\\b\", normalizada):",
  "                achados.append((n, termo, SUGESTOES.get(termo, \"remover o termo\")))",
  "    return achados",
  "",
  "def main() -> int:",
  "    total = 0",
  "    for padrao in ALVOS:",
  "        for arquivo in Path(\".\").glob(padrao):",
  "            for linha, termo, sugestao := ... :  # ver implementacao completa",
  "                print(f\"{arquivo}:{linha} termo proibido '{termo}'\")",
  "                print(f\"    use: {sugestao}\")",
  "                total += 1",
  "    if total:",
  "        print(f\"\\n{total} violacao(oes) de vocabulario controlado. Ver DOC-08.\")",
  "        return 1",
  "    return 0",
  "",
  "if __name__ == \"__main__\":",
  "    sys.exit(main())",
]));
body.push(p("Dois detalhes do desenho merecem nota. O primeiro é a normalização de acentos: sem ela, " +
  "bastaria escrever a palavra com acento para escapar da verificação. O segundo é a delimitação por " +
  "fronteira de palavra, que evita o falso positivo mais óbvio: desvio padrão é termo estatístico " +
  "legítimo e aparece com frequência no motor de detecção."));
body.push(p("A anotação de exceção existe para casos genuínos, como um campo que armazene o texto " +
  "literal de uma contestação enviada por um ente, que pode conter qualquer palavra. Toda exceção exige " +
  "justificativa no código e é auditada na revisão."));

body.push(pageBreak());
body.push(h1("3. Estratégia de testes"));
body.push(table(["Camada", "O que cobre", "Meta", "Onde roda"], [2000, 3800, 1400, 2400], [
  ["Unitário", "Domínio, cálculo de score, transformações", "80% mínimo", "Todo commit"],
  ["Regra", "Cada regra contra casos sintéticos positivos e negativos", "100% das regras", "Todo commit"],
  ["Contrato de fonte", "Esquema esperado de cada fonte externa", "Todas as fontes com API", "Diário"],
  ["Integração", "Pipeline bruto até indício em base de teste", "Fluxos principais", "Toda entrega"],
  ["Ponta a ponta", "Casos de uso críticos pelo portal", "UC-03, UC-08, UC-11", "Toda entrega"],
  ["Vocabulário", "Ausência de termo proibido", "Obrigatório", "Todo commit"],
]));

body.push(h2("3.1 Teste de regra"));
body.push(p("Cada regra do catálogo tem um arquivo de teste com, no mínimo, um caso que deve disparar, " +
  "um caso que não deve disparar e um caso de falso positivo conhecido documentado no DOC-07. O último " +
  "é o mais valioso: ele registra no código a limitação já identificada."));
body.push(code([
  "def test_b01_dispara_quando_soma_ultrapassa_limite():",
  "    \"\"\"Cinco dispensas de objeto similar, mesmo fornecedor, 180 dias.\"\"\"",
  "    contratacoes = [",
  "        dispensa(valor=15_000, objeto=\"material de expediente\", dia=d)",
  "        for d in (10, 45, 80, 120, 160)",
  "    ]   # soma = 75.000 > limite de 65.492,11",
  "    indicios = executar_regra(\"B-01\", contratacoes, limite=65_492.11)",
  "",
  "    assert len(indicios) == 1",
  "    assert indicios[0].valores_observados[\"soma\"] == 75_000",
  "    assert indicios[0].valores_observados[\"limite_aplicado\"] == 65_492.11",
  "",
  "def test_b01_nao_dispara_para_objetos_distintos():",
  "    \"\"\"Similaridade textual baixa nao deve agrupar.\"\"\"",
  "    contratacoes = [",
  "        dispensa(valor=40_000, objeto=\"material de expediente\", dia=10),",
  "        dispensa(valor=40_000, objeto=\"reforma de cobertura escolar\", dia=40),",
  "    ]",
  "    assert executar_regra(\"B-01\", contratacoes) == []",
  "",
  "def test_b01_falso_positivo_conhecido_unidades_gestoras_autonomas():",
  "    \"\"\"DOC-07, B-01: limites sao contados por unidade gestora autonoma.",
  "",
  "    Documenta a limitacao: sem o dado de autonomia da UG, a regra agrupa",
  "    indevidamente. O teste garante que, QUANDO o dado existe, ela respeita.",
  "    \"\"\"",
  "    contratacoes = [",
  "        dispensa(valor=40_000, ug=\"secretaria_saude\", autonoma=True, dia=10),",
  "        dispensa(valor=40_000, ug=\"secretaria_educacao\", autonoma=True, dia=40),",
  "    ]",
  "    assert executar_regra(\"B-01\", contratacoes) == []",
]));

body.push(h2("3.2 Teste de contrato de fonte"));
body.push(p("Fontes externas mudam sem aviso. O teste de contrato consome a fonte real diariamente e " +
  "valida apenas o esquema, não o conteúdo, alarmando quando um campo esperado desaparece ou muda de " +
  "tipo. É o que transforma a quebra silenciosa da ADR-003 em alarme."));
body.push(p("As fixtures são amostras reais capturadas de cada fonte e versionadas no repositório. Elas " +
  "permitem que todo o pipeline seja testado sem rede, e servem de documentação viva do formato real de " +
  "cada fonte, que costuma divergir da documentação oficial."));

body.push(h1("4. Git e integração contínua"));
body.push(h2("4.1 Ramos e commits"));
body.push(table(["Item", "Convenção"], [2400, 7200], [
  ["Ramo principal", "main, sempre implantável"],
  ["Ramo de trabalho", "tipo/descricao-curta, por exemplo feat/conector-pncp"],
  ["Formato de commit", "Conventional Commits em português"],
  ["Tipos aceitos", "feat, fix, refactor, test, docs, chore, perf"],
  ["Escopo", "Nome do pacote, por exemplo feat(deteccao):"],
  ["Tamanho", "Um commit por mudança lógica coesa"],
]));
body.push(code([
  "feat(deteccao): adiciona regra B-01 de fracionamento por agregacao",
  "",
  "Agrupa contratacoes diretas do mesmo ente e fornecedor com objeto",
  "similar em janela de 180 dias e compara a soma com o limite legal",
  "vigente na data de cada ato.",
  "",
  "O limite vem de parametros_legais com vigencia datada, para que",
  "reprocessamentos historicos usem o valor correto do periodo.",
  "",
  "Ref: DOC-07 familia B, RF-DE-06",
]));
body.push(p("A mensagem responde por que, não o que: o diff já mostra o que mudou. A referência ao " +
  "documento e ao requisito mantém a rastreabilidade exigida pelo DOC-02."));

body.push(h2("4.2 Estágios da integração contínua"));
body.push(table(["Estágio", "Verificação", "Bloqueia?"], [2200, 5600, 1800], [
  ["Formatação", "Formatador e organizador de imports", "Sim"],
  ["Análise estática", "Linter e verificação de tipos", "Sim"],
  ["Vocabulário", "Verificador do DOC-08", "Sim"],
  ["Testes unitários", "Suíte completa com cobertura mínima", "Sim"],
  ["Testes de regra", "Todas as regras do catálogo", "Sim"],
  ["Segurança", "Vulnerabilidade em dependências e segredo vazado", "Sim"],
  ["Testes de integração", "Pipeline em base de teste", "Sim na entrega"],
  ["Contrato de fonte", "Esquema das fontes externas reais", "Não; alarma"],
]));

body.push(pageBreak());
body.push(h1("5. Definição de pronto"));
body.push(p("Uma entrega só é considerada pronta quando todos os itens abaixo são verdadeiros. A lista " +
  "é verificada na revisão, não na autoavaliação de quem desenvolveu."));
body.push(numbered("O código atende ao requisito referenciado e o número do requisito consta no commit."));
body.push(numbered("Existem testes cobrindo o caminho feliz, ao menos um caminho de erro e, para regra, o falso positivo conhecido."));
body.push(numbered("A integração contínua está verde em todos os estágios bloqueantes."));
body.push(numbered("Nenhum valor legal foi fixado no código; parâmetros datados foram usados."));
body.push(numbered("Textos destinados ao público passaram pelo verificador de vocabulário."));
body.push(numbered("Se houve decisão arquitetural relevante, existe ADR correspondente."));
body.push(numbered("Se o esquema canônico mudou, existe migração e os dois lados da fronteira foram atualizados."));
body.push(numbered("Se uma regra foi adicionada ou alterada, sua explicação pública foi aprovada pelo comitê de metodologia."));
body.push(numbered("Se uma fonte foi adicionada, existe fixture versionada e teste de contrato."));
body.push(numbered("Nenhum segredo, credencial ou dado pessoal real foi incluído no repositório."));

body.push(h1("6. Roteiro de revisão de código"));
body.push(h2("6.1 Específico deste projeto"));
body.push(bullet("O texto exibido ao público está em linguagem neutra e evita qualquer inferência sobre conduta?"));
body.push(bullet("Valores legais vêm de parâmetro datado, e a consulta usa a data do ato e não a data atual?"));
body.push(bullet("O indício produzido carrega regra, versão, parâmetros e ao menos um documento fonte?"));
body.push(bullet("A transformação preserva a linhagem até o artefato bruto?"));
body.push(bullet("Dado pessoal foi minimizado e documento de pessoa física mascarado antes da camada consultável?"));
body.push(bullet("A regra nova entrou em modo silencioso, e não diretamente em publicação?"));
body.push(bullet("Erro de coleta está sendo distinguido de ausência de publicação pelo ente?"));

body.push(h2("6.2 Geral"));
body.push(bullet("O nome da função descreve o que ela faz, no vocabulário do domínio?"));
body.push(bullet("Há tratamento explícito para dado ausente, que é a situação normal neste projeto?"));
body.push(bullet("A operação é idempotente, considerando que todo processamento pode ser repetido?"));
body.push(bullet("Há teste que falharia se esta mudança fosse revertida?"));
body.push(bullet("Alguma consulta nova varre partição inteira sem filtro por exercício ou ente?"));

body.push(h1("7. Observabilidade no código"));
body.push(p("Registro estruturado em todo o pipeline, com campos obrigatórios que permitem reconstruir " +
  "qualquer execução: identificador da execução, fonte, ente, etapa e versão do componente."));
body.push(code([
  "log.info(",
  "    \"coleta_concluida\",",
  "    execucao_id=ctx.execucao_id,",
  "    fonte=fonte.identificador,",
  "    ente_codigo_ibge=fonte.ente.codigo_ibge,",
  "    artefatos=len(artefatos),",
  "    bytes_total=total_bytes,",
  "    duracao_ms=duracao,",
  "    versao_spec=fonte.versao_spec,",
  ")",
  "",
  "# Metrica que sustenta o alarme mais importante do sistema (DOC-04, secao 8):",
  "# volume coletado por fonte, comparado a media movel da propria fonte.",
  "metricas.registrar(\"lumen.coleta.artefatos\", len(artefatos),",
  "                   tags={\"fonte\": fonte.identificador})",
]));
body.push(callout("Nunca registrar em log", [
  "Documento de pessoa física sem máscara, conteúdo integral de artefato coletado, token de API ou " +
  "credencial de qualquer natureza. O registro estruturado é lido por ferramentas de observabilidade " +
  "que podem ter política de acesso distinta da do banco de dados.",
], "red"));

L.buildDoc({
  codigo: "DOC-09",
  titulo: "Padrões de Código",
  subtitulo: "Convenções, testes, integração contínua e definição de pronto",
  body,
  outFile: "../docs/DOC-09_Padroes_de_Codigo.docx",
});
