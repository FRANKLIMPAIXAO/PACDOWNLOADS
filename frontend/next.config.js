/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Output standalone reduz a imagem Docker em ~80%: o build copia somente os
  // arquivos necessarios (sem node_modules inteiro) para .next/standalone.
  // Veja docker-compose.production.yml + frontend/Dockerfile.
  output: "standalone",
  // Convite do portal: se o link vier sem /portal (ex.: PORTAL_URL apontando pro
  // dominio raiz), redireciona pra pagina certa. O Next preserva o ?token=.
  async redirects() {
    return [
      { source: "/definir-senha", destination: "/portal/definir-senha", permanent: false },
    ];
  },
};

module.exports = nextConfig;
