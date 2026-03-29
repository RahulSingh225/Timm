import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db/index';
import { agentRuns } from '@/db/schema';
import OpenAI from 'openai';

// Initialize OpenAI client pointed at Local LLM (Ollama)
const openai = new OpenAI({
    baseURL: process.env.OPENAI_API_BASE || 'http://localhost:11434/v1',
    apiKey: process.env.OPENAI_API_KEY || 'ollama',
});

export async function POST(req: NextRequest) {
    const runStartTime = Date.now();
    let llmPromptPreview = '';
    let llmResponsePreview = '';
    const aiModel = process.env.AI_MODEL || 'llama3.2';

    try {
        const body = await req.json();
        const query = body.message || body.query;
        const history = body.history || [];

        if (!query) {
            return NextResponse.json({ error: 'Message/Query is required' }, { status: 400 });
        }

        // ==========================================
        // 1. VANILLA MODE: NO SYSTEM PROMPT / CONTEXT
        // ==========================================
        const messages = history.map((msg: any) => ({
            role: msg.role === 'user' ? 'user' : 'assistant',
            content: msg.content,
        }));

        // Add the current message
        messages.push({ role: 'user', content: query });

        llmPromptPreview = query.substring(0, 500);

        // ==========================================
        // 2. CALL LOCAL LLM API
        // ==========================================
        const response = await openai.chat.completions.create({
            model: aiModel,
            messages: messages,
            temperature: 0.7, // Slightly higher for vanilla chat
            max_tokens: 1000,
        });

        const responseText = response.choices[0]?.message?.content || "No response generated.";
        llmResponsePreview = responseText.substring(0, 500);

        const durationMs = Date.now() - runStartTime;

        // Log the agent run for observability
        try {
            await db.insert(agentRuns).values({
                agentName: 'vanilla_chat',
                runStatus: 'SUCCESS',
                durationMs,
                llmModel: aiModel,
                llmPromptTokens: response.usage?.prompt_tokens ?? null,
                llmCompletionTokens: response.usage?.completion_tokens ?? null,
                llmPromptPreview,
                llmResponsePreview,
                metadata: { mode: 'vanilla', query: query.substring(0, 200) },
            });
        } catch (logErr) {
            console.error('Failed to log agent run:', logErr);
        }

        return NextResponse.json({ reply: responseText, response: responseText });

    } catch (error: any) {
        const durationMs = Date.now() - runStartTime;
        // Log failure
        try {
            await db.insert(agentRuns).values({
                agentName: 'vanilla_chat',
                runStatus: 'FAILED',
                durationMs,
                llmModel: aiModel,
                llmPromptPreview: llmPromptPreview || null,
                errorMessage: error.message?.substring(0, 1000),
            });
        } catch (logErr) {
            console.error('Failed to log agent run error:', logErr);
        }

        console.error('Vanilla Chat API Error:', error);
        return NextResponse.json({ error: error.message || 'Failed to generate response' }, { status: 500 });
    }
}
