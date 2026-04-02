import { NextRequest } from 'next/server';
import amqp from 'amqplib';

// This forces Next.js to treat this route as a dynamic, long-running stream
export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
    let connection: any = null;
    let channel: any = null;

    const stream = new ReadableStream({
        async start(controller) {
            try {
                // Connect to your RabbitMQ container via env vars
                const RABBITMQ_URL = process.env.RABBITMQ_URL as string;
                connection = await amqp.connect(RABBITMQ_URL);
                connection.on('error', (err: any) => console.error('[SSE API] Connection Error:', err));
                
                channel = await connection.createChannel();
                channel.on('error', (err: any) => console.error('[SSE API] Channel Error:', err));

                const exchange = 'market_data_exchange';
                await channel.assertExchange(exchange, 'topic', { durable: true });

                // Create an exclusive, temporary queue just for this browser session
                const q = await channel.assertQueue('', { exclusive: true });

                // Listen to ALL alerts from the Swing and Scalper agents
                await channel.bindQueue(q.queue, exchange, 'alert.#');

                console.log('[SSE API] Connected to RabbitMQ. Streaming alerts to dashboard...');

                channel.consume(q.queue, (msg: any) => {
                    if (msg) {
                        const payload = msg.content.toString();
                        // Format for Server-Sent Events: "data: {json}\n\n"
                        controller.enqueue(new TextEncoder().encode(`data: ${payload}\n\n`));
                        channel!.ack(msg);
                    }
                });

                // Keep the connection alive if the client drops
                req.signal.addEventListener('abort', () => {
                    console.log('[SSE API] Client disconnected. Closing RabbitMQ channel.');
                    channel?.close();
                    connection?.close();
                    controller.close();
                });

            } catch (error) {
                console.error('[SSE API] Error:', error);
                controller.error(error);
            }
        }
    });

    return new Response(stream, {
        headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
        },
    });
}