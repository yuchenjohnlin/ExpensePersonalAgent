# The page of the rebuilt app (deploy/README.md): built once, then served by nginx, which also
# passes /api/ to the API container (nginx.conf; pm/decisions/nginx-reverse-proxy.md).
FROM node:22-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.28-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
