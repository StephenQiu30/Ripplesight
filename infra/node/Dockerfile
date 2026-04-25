FROM node:22-alpine

WORKDIR /app/frontend/web

ENV NODE_ENV=production \
    NEXT_PUBLIC_API_BASE_URL=http://api:8000 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

COPY . /app

RUN npm ci

WORKDIR /app/frontend/web
RUN npm run api:gen && npm run build

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
