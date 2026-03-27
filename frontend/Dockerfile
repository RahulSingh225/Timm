FROM node:18-alpine

WORKDIR /app

# Install dependencies based on the preferred package manager
COPY package*.json ./
RUN npm install

# Copy source and build
COPY . .
RUN npm run build

# Next.js collects completely anonymous telemetry data about general usage.
# Learn more here: https://nextjs.org/telemetry
# Uncomment the following line in case you want to disable telemetry during the build.
# ENV NEXT_TELEMETRY_DISABLED 1

EXPOSE 3000

ENV PORT 3000

# Next.js uses CMD ["npm", "start"] but we'll use dev mode if it's for easier debugging,
# or start for production. Standard is start.
CMD ["npm", "run", "start"]
