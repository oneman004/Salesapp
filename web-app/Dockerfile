# Web Builder
FROM node:20.11-alpine AS web-builder
WORKDIR /usr/src/app
COPY package.json package-lock.json* pnpm-lock.yaml* ./
RUN npm ci --prefer-offline --no-audit --progress=false
COPY . .
RUN npm run build

# Production image
FROM node:20.11-alpine AS web
WORKDIR /usr/src/app
COPY --from=web-builder /usr/src/app/.next ./.next
COPY --from=web-builder /usr/src/app/node_modules ./node_modules
COPY --from=web-builder /usr/src/app/package.json .
CMD ["npm", "start"]
