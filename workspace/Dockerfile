FROM node:24.19.0-alpine AS dependencies

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
ENV NEXT_TELEMETRY_DISABLED=1

RUN apk add --no-cache git \
    && corepack enable \
    && corepack prepare pnpm@12.3.4 --activate

WORKDIR /srv/workspace
COPY workspace/package.json workspace/pnpm-lock.yaml workspace/pnpm-workspace.yaml ./
COPY workspace/patches ./patches
RUN pnpm install --frozen-lockfile

FROM dependencies AS development
COPY --chown=node:node . /srv/
RUN chown node:node /srv /srv/workspace
USER node
ENV DOCS_SOURCE_ROOT=/source HOST=0.0.0.0 PORT=8080
EXPOSE 8080
CMD ["node", "scripts/watch.mjs"]

FROM dependencies AS builder
# Root documents and referenced source paths are needed by the existing validator.
COPY . /srv/
RUN pnpm build && pnpm check

FROM nginxinc/nginx-unprivileged:1.29-alpine@sha256:0c79d56aee561a1d81c63f00eee5fb5fe29279560cdc55e91425133104c7fbe6 AS runner

COPY workspace/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /srv/workspace/out /usr/share/nginx/html/Ripplesight

EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
