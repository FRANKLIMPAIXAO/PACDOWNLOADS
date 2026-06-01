/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Output standalone reduz a imagem Docker em ~80%: o build copia somente os
  // arquivos necessarios (sem node_modules inteiro) para .next/standalone.
  // Veja docker-compose.production.yml + frontend/Dockerfile.
  output: "standalone",
};

module.exports = nextConfig;
