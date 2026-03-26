import { NextRequest } from 'next/server';
import amqp from 'amqplib';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
    let connection: any = null;
    let channel: any = null;

    const stream = new ReadableStream({
        async start(controller) {
            try {
                const RABBITMQ_URL = process.env.RABBITMQ_URL as string;
                connection = await amqp.connect(RABBITMQ_URL);
                channel = await connection.createChannel();

                const exchange = 'market_data_exchange';
                await channel.assertExchange(exchange, 'topic', { durable: true });

                const q = await channel.assertQueue('', { exclusive: true });

                // Bind specifically for vector alerts
                await channel.bindQueue(q.queue, exchange, 'candle.vector');

                console.log('[SSE Vector API] Connected to RabbitMQ. Streaming vector signals...');

                channel.consume(q.queue, (msg: any) => {
                    if (msg) {
                        const payload = msg.content.toString();
                        // SendSSE
                        controller.enqueue(new TextEncoder().encode(`data: ${payload}\n\n`));
                        channel!.ack(msg);
                    }
                });

                req.signal.addEventListener('abort', () => {
                    console.log('[SSE Vector API] Client disconnected. Closing channel.');
                    channel?.close();
                    connection?.close();
                    controller.close();
                });

            } catch (error) {
                console.error('[SSE Vector API] Error:', error);
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
