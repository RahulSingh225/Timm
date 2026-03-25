import amqp from 'amqplib';
import { db } from './src/db/index';
import { alerts } from './src/db/schema';
import * as dotenv from 'dotenv';

// Load environment variables for the worker
dotenv.config({ path: '.env.local' });

const RABBITMQ_URL = process.env.RABBITMQ_URL || 'amqp://admin:supersecretpassword@localhost:5672';
const EXCHANGE_NAME = 'market_data_exchange';

async function startDatabaseWorker() {
    try {
        console.log(`[DB WORKER] Connecting to RabbitMQ at ${RABBITMQ_URL}...`);
        const connection = await amqp.connect(RABBITMQ_URL);
        const channel = await connection.createChannel();

        console.log(`[DB WORKER] Connected. Setting up exchange and queues...`);
        await channel.assertExchange(EXCHANGE_NAME, 'topic', { durable: true });

        // Ensure the queue exists and binds to all alerts
        const q = await channel.assertQueue('db_alerts_logging_queue', { durable: true });
        await channel.bindQueue(q.queue, EXCHANGE_NAME, 'alert.#');

        console.log('[DB WORKER] Listening for alerts to save to PostgreSQL. To exit press CTRL+C');

        channel.consume(q.queue, async (msg) => {
            if (msg !== null) {
                try {
                    const alertData = JSON.parse(msg.content.toString());
                    console.log(`[DB WORKER] Received alert for ${alertData.symbol} from ${alertData.agent}`);

                    // Insert into Drizzle ORM
                    await db.insert(alerts).values({
                        agent: alertData.agent || 'Unknown',
                        symbol: alertData.symbol,
                        closePrice: alertData.close_price ? alertData.close_price.toString() : null,
                        signals: alertData.signals || [],
                        brief: alertData.brief || null, // Might be empty until Gemini updates it, 
                        // or Head Analyst can be updated to send its brief here
                    });

                    console.log(`[DB WORKER] Successfully saved alert for ${alertData.symbol} to database.`);
                    channel.ack(msg);
                } catch (dbError) {
                    console.error('[DB WORKER] Failed to save to database:', dbError);
                    // depending on policy, you could nack, but we don't want to block the queue endlessly for bad JSON
                    channel.nack(msg, false, false);
                }
            }
        });

    } catch (error) {
        console.error('[DB WORKER] Error setting up worker:', error);
    }
}

startDatabaseWorker();
