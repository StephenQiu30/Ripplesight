FROM node:22-alpine

WORKDIR /workspace

COPY apps/web/package*.json ./apps/web/
RUN cd apps/web && npm install

COPY . .
