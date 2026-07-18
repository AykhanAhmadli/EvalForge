FROM node:20-alpine

WORKDIR /app/frontend

COPY frontend/package*.json ./
COPY package.json /app/package.json
RUN npm install

COPY frontend ./

EXPOSE 5173
