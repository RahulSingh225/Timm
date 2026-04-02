import amqp from 'amqplib';
import { db } from './src/db/index';
import { marketAlerts } from './src/db/schema';
import * as dotenv from 'dotenv';

// Load environment variables for the worker
dotenv.config({ path: '.env.local' });

const RABBITMQ_URL = process.env.RABBITMQ_URL as string;
const EXCHANGE_NAME = 'market_data_exchange';

async function startDatabaseWorker() {
    try {
        console.log(`[DB WORKER] Connecting to RabbitMQ at ${RABBITMQ_URL}...`);
        const connection = await amqp.connect(RABBITMQ_URL);
        
        // Handle connection errors/closures
        connection.on('error', (err) => {
            console.error('[DB WORKER] RabbitMQ connection error:', err);
        });
        connection.on('close', () => {
            console.warn('[DB WORKER] RabbitMQ connection closed. Reconnecting in 5s...');
            setTimeout(startDatabaseWorker, 5000);
        });

        const channel = await connection.createChannel();
        channel.on('error', (err) => {
            console.error('[DB WORKER] RabbitMQ channel error:', err);
        });

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
                    await db.insert(marketAlerts).values({
                        agentSource: alertData.agent || 'Unknown',
                        symbol: alertData.symbol,
                        signalType: alertData.signal_type || alertData.signalType || 'NEUTRAL',
                        closePrice: alertData.close_price ? Math.round(Number(alertData.close_price)) : null,
                        signals: alertData.signals || [],
                        summary: alertData.brief || null, 
                    });

                    console.log(`[DB WORKER] Successfully saved alert for ${alertData.symbol} to database.`);
                    channel.ack(msg);
                } catch (dbError) {
                    console.error('[DB WORKER] Failed to save to database:', dbError);
                    // nack and don't requeue if it's a parsing error or schema mismatch to avoid poison messages
                    channel.nack(msg, false, false);
                }
            }
        });

    } catch (error) {
        console.error('[DB WORKER] Error setting up worker:', error);
        console.log('[DB WORKER] Retrying in 5s...');
        setTimeout(startDatabaseWorker, 5000);
    }
}

startDatabaseWorker();
