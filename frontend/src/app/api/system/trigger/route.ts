import { NextResponse } from 'next/server';
import amqp from 'amqplib';

export async function POST(req: Request) {
    try {
        const { task } = await req.json();

        if (!task) {
            return NextResponse.json({ error: 'Task is required' }, { status: 400 });
        }

        const RABBITMQ_URL = process.env.RABBITMQ_URL as string;
        const connection = await amqp.connect(RABBITMQ_URL);
        const channel = await connection.createChannel();

        const queueName = 'system_commands';
        // Ensure the queue exists
        await channel.assertQueue(queueName, { durable: true });

        const payload = JSON.stringify({ task });

        // Push directly to the queue instead of an exchange
        const sent = channel.sendToQueue(queueName, Buffer.from(payload), {
            persistent: true
        });

        if (sent) {
            console.log(`[API Trigger] Queued manual task: ${task}`);
            // Small delay to ensure message handles (fire-and-forget style)
            setTimeout(() => {
                connection.close();
            }, 500);

            return NextResponse.json({ message: `Trigger executed for ${task}` });
        } else {
            return NextResponse.json({ error: 'Message broker failed to queue task.' }, { status: 500 });
        }

    } catch (error: any) {
        console.error('[API Trigger Error]:', error);
        return NextResponse.json({ error: error.message }, { status: 500 });
    }
}