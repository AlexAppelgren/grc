# Compliance Watch frontend. Multi-stage, non-root, production Next server
# (playbook 2.3, 12; DECISIONS D-16: container-only, nothing Railway-specific).
# Build context is the frontend/ directory.

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Public build-time settings. NEXT_PUBLIC_* values are inlined at build time,
# so the image is per environment for these two only.
ARG NEXT_PUBLIC_API_URL=""
ARG NEXT_PUBLIC_PRODUCT_NAME="Compliance Watch"
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL NEXT_PUBLIC_PRODUCT_NAME=$NEXT_PUBLIC_PRODUCT_NAME
# next.config.ts switches to `output: 'standalone'` on this flag.
ENV NEXT_OUTPUT_STANDALONE=1
RUN npm run build:tokens && npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
# `output: 'standalone'` emits a self-contained server.js; it is what
# `next start` becomes for a standalone build (Next.js deployment docs), so the
# image runs it directly instead of shipping the whole node_modules tree.
COPY --from=builder --chown=node:node /app/public ./public
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
