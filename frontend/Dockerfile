# --- Etapa 1: compilar el frontend de Astro a estáticos -------------------------
FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# frontend/.env (solo PUBLIC_*) se lee aquí, en tiempo de compilación.
RUN npm run build

# --- Etapa 2: Caddy sirviendo los estáticos y el proxy /api --------------------
FROM caddy:2.10-alpine
COPY --from=build /app/dist /srv
# El Caddyfile se monta desde la raíz del proyecto en docker-compose.yml.
