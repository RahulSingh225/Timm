import { configDotenv } from 'dotenv';
import { defineConfig } from 'drizzle-kit';
configDotenv();

export default defineConfig({
  schema: './src/db/schema.ts',
  out: './drizzle',
  dialect: 'postgresql',
  dbCredentials: {
    url: 'postgres://dbadmin:Test@123@13.235.69.226:5432/vguard',
  },
});
