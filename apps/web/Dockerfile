FROM node:22-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY next.config.ts tsconfig.json next-env.d.ts ./
COPY app ./app
COPY lib ./lib

ENV HOSTNAME=0.0.0.0 \
    PORT=3000

RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
