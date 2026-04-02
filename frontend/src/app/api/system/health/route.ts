import { NextResponse } from 'next/server';
import amqp from 'amqplib';
import { db } from '@/db';
import { sql } from 'drizzle-orm';

export const dynamic = 'force-dynamic';

interface HealthStatus {
    database: {
        status: 'connected' | 'error';
        latencyMs: number;
        error?: string;
    };
    rabbitmq: {
        status: 'connected' | 'error';
        latencyMs: number;
        queues: {
            name: string;
            messageCount: number;
            consumerCount: number;
        }[];
        error?: string;
    };
    llm: {
        status: 'connected' | 'error';
        latencyMs: number;
        model: string;
        baseUrl: string;
        error?: string;
    };
    backend: {
        status: 'connected' | 'error';
        latencyMs: number;
        workersActive: number;
        error?: string;
    };
}

export async function GET() {
    const health: HealthStatus = {
        database: { status: 'error', latencyMs: 0 },
        rabbitmq: { status: 'error', latencyMs: 0, queues: [] },
        llm: { status: 'error', latencyMs: 0, model: '', baseUrl: '' },
        backend: { status: 'error', latencyMs: 0, workersActive: 0 },
    };

    // 1. Database Health
    try {
        const dbStart = Date.now();
        await db.execute(sql`SELECT 1`);
        health.database = {
            status: 'connected',
            latencyMs: Date.now() - dbStart,
        };
    } catch (e: any) {
        health.database = {
            status: 'error',
            latencyMs: 0,
            error: e.message?.substring(0, 200),
        };
    }

    // 2. RabbitMQ Health + Queue Stats
    let rmqConnection: any = null;
    try {
        const rmqStart = Date.now();
        const RABBITMQ_URL = process.env.RABBITMQ_URL as string;
        rmqConnection = await amqp.connect(RABBITMQ_URL);
        const rmqLatency = Date.now() - rmqStart;

        // Check key queues
        const queueNames = [
            'swing_analysis_queue',
            'vault_db_queue',
            'system_commands',
            'db_alerts_logging_queue',
        ];

        const queues = [];
        for (const qName of queueNames) {
            let tempChannel: any = null;
            try {
                // Create a temporary channel for each check to avoid killing the main connection
                tempChannel = await rmqConnection.createChannel();
                // Avoid uncaught exceptions if the channel closes due to 404
                tempChannel.on('error', () => {}); 
                
                const qInfo = await tempChannel.checkQueue(qName);
                queues.push({
                    name: qName,
                    messageCount: qInfo.messageCount,
                    consumerCount: qInfo.consumerCount,
                });
                await tempChannel.close();
            } catch {
                // Queue may not exist yet — that's fine
                queues.push({
                    name: qName,
                    messageCount: -1,
                    consumerCount: 0,
                });
                // No need to close tempChannel here as it's likely already closed by RabbitMQ on error
            }
        }


        
        health.rabbitmq = {
            status: 'connected',
            latencyMs: rmqLatency,
            queues,
        };
    } catch (e: any) {
        health.rabbitmq = {
            status: 'error',
            latencyMs: 0,
            queues: [],
            error: e.message?.substring(0, 200),
        };
    } finally {
        try { rmqConnection?.close(); } catch {}
    }

    // 3. LLM (Ollama) Health
    const llmBaseUrl = process.env.OPENAI_API_BASE || 'http://localhost:11434/v1';
    const llmModel = process.env.AI_MODEL || 'llama3.2';
    try {
        const llmStart = Date.now();
        // Ollama exposes /api/tags or the OpenAI compat /v1/models
        const modelsUrl = llmBaseUrl.replace('/v1', '/api/tags');
        const res = await fetch(modelsUrl, {
            signal: AbortSignal.timeout(5000),
        });

        if (res.ok) {
            const data = await res.json();
            const models = data.models?.map((m: any) => m.name) || [];
            health.llm = {
                status: 'connected',
                latencyMs: Date.now() - llmStart,
                model: llmModel,
                baseUrl: llmBaseUrl,
            };
        } else {
            throw new Error(`LLM responded with status ${res.status}`);
        }
    } catch (e: any) {
        health.llm = {
            status: 'error',
            latencyMs: 0,
            model: llmModel,
            baseUrl: llmBaseUrl,
            error: e.message?.substring(0, 200),
        };
    }

    // 4. Python Backend (FastAPI) Health
    const backendUrl = process.env.PYTHON_API_URL || 'http://localhost:8000';
    try {
        const beStart = Date.now();
        const res = await fetch(`${backendUrl}/`, {
            cache: 'no-store',
            signal: AbortSignal.timeout(3000),
        });
        if (res.ok) {
            const data = await res.json();
            health.backend = {
                status: 'connected',
                latencyMs: Date.now() - beStart,
                workersActive: data.workers_active || 0,
            };
        } else {
            throw new Error(`Backend responded ${res.status}`);
        }
    } catch (e: any) {
        health.backend = {
            status: 'error',
            latencyMs: 0,
            workersActive: 0,
            error: e.message?.substring(0, 200),
        };
    }

    return NextResponse.json(health);
}
