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
  // Headers de segurança em todas as páginas (anti clickjacking, MIME-sniffing,
  // vazamento de referrer) + HSTS. Sem CSP por enquanto (precisa de ajuste fino
  // pra não quebrar o app; fica como próximo passo).
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(self), geolocation=()" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
