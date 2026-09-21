FROM node:20-alpine

WORKDIR /app
COPY package.json package-lock.json ./
# Retry slow/flaky downloads; the cache mount keeps packages between
# builds so a failed build doesn't start from scratch.
RUN --mount=type=cache,target=/root/.npm \
    npm ci --fetch-retries=10 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=600000

COPY . .

EXPOSE 3000
CMD ["npx", "next", "dev", "-H", "0.0.0.0", "-p", "3000"]
