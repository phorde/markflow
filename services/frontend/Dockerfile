FROM node:20-alpine AS deps
WORKDIR /app/frontend

COPY services/frontend/package.json services/frontend/package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app/frontend
ARG NEXT_PUBLIC_MARKFLOW_API_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_MARKFLOW_API_URL=$NEXT_PUBLIC_MARKFLOW_API_URL
COPY --from=deps /app/frontend/node_modules ./node_modules
COPY services/frontend/ ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app/frontend
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

COPY --from=builder /app/frontend/.next ./.next
COPY --from=builder /app/frontend/package.json ./package.json
COPY --from=builder /app/frontend/node_modules ./node_modules

EXPOSE 3000

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0", "-p", "3000"]
