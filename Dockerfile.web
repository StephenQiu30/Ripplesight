FROM node:22-alpine

WORKDIR /workspace

COPY apps/web ./apps/web

WORKDIR /workspace/apps/web
RUN npm install

ENV NEXT_PUBLIC_API_BASE_URL=/
ENV NODE_ENV=production

RUN npm run build

EXPOSE 3000

CMD ["npm", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
