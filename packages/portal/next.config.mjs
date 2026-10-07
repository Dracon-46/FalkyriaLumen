// Portal estático: `next build` gera `out/`, que qualquer servidor de arquivos
// ou CDN serve. Não há servidor Node em produção (ADR-019): os dados chegam
// como arquivos JSON em /dados/eleicoes, gravados pelo coletor.

/** @type {import('next').NextConfig} */
const config = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  reactStrictMode: true,
  // Os testes de unidade ficam fora da compilação do site
  pageExtensions: ["tsx"],
};

export default config;
