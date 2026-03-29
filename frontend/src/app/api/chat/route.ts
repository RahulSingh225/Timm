import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db/index';
import { marketAlerts, fiiDiiFlows, newsEvents, participantData, globalCues, screenedStocks, agentRuns } from '@/db/schema';
import { desc, eq } from 'drizzle-orm';
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

    try {
        const body = await req.json();
        const query = body.message || body.query;
        const history = body.history || [];
        const symbol = body.symbol;

        if (!query) {
            return NextResponse.json({ error: 'Message/Query is required' }, { status: 400 });
        }

        // ==========================================
        // 1. RETRIEVE ON-PREMISES CONTEXT (The RAG)
        // ==========================================
        let recentAlerts;
        if (symbol) {
            recentAlerts = await db.select()
                .from(marketAlerts)
                .where(eq(marketAlerts.symbol, symbol))
                .orderBy(desc(marketAlerts.createdAt))
                .limit(5);
        } else {
            recentAlerts = await db.select()
                .from(marketAlerts)
                .orderBy(desc(marketAlerts.createdAt))
                .limit(5);
        }

        const latestSmartMoney = await db.select()
            .from(fiiDiiFlows)
            .orderBy(desc(fiiDiiFlows.tradeDate))
            .limit(1);

        const recentParticipantData = await db.select()
            .from(participantData)
            .orderBy(desc(participantData.tradeDate))
            .limit(4);

        const recentNews = await db.select()
            .from(newsEvents)
            .orderBy(desc(newsEvents.publishedAt))
            .limit(3);

        const latestGlobalCues = await db.select()
            .from(globalCues)
            .orderBy(desc(globalCues.capturedAt))
            .limit(1);

        const recentSetups = await db.select()
            .from(screenedStocks)
            .orderBy(desc(screenedStocks.confidence))
            .limit(3);

        // ==========================================
        // 2. CONSTRUCT THE CONTEXT ENVELOPE
        // ==========================================
        const systemPrompt = `
      You are an elite quantitative trading desk co-pilot for the Indian Stock Market (NSE/BSE).
      Do not give generic financial disclaimers. Act strictly as a ruthless, data-driven analyst.
      
      Use the following real-time database context to answer the user's query:

      [SMART MONEY POSITIONING (FII/DII)]
      ${latestSmartMoney.length > 0 ? `
        Date: ${latestSmartMoney[0].tradeDate}
        FII Net Cash: ₹${latestSmartMoney[0].fiiNetCash} Cr
        DII Net Cash: ₹${latestSmartMoney[0].diiNetCash} Cr
        FII Index Futures Net: ${latestSmartMoney[0].fiiIdxFutNet} contracts
        Market PCR: ${latestSmartMoney[0].pcr}
        System Sentiment Score: ${latestSmartMoney[0].sentimentScore}/100
      ` : 'No recent general FII/DII aggregate flows available.'}
      
      [GLOBAL MACRO CUES]
      ${latestGlobalCues.length > 0 ? `
        Bias: ${latestGlobalCues[0].overallBias}
        VIX: ${latestGlobalCues[0].vixValue} (${latestGlobalCues[0].vixChangePct}%)
        SPY: ${latestGlobalCues[0].spyChangePct}% | QQQ: ${latestGlobalCues[0].qqqChangePct}%
        SGX NIFTY: ${latestGlobalCues[0].sgxNifty} (${latestGlobalCues[0].sgxChangePct}%)
      ` : 'No pre-market global cues available.'}

      [TOP SCREENED INTRADAY SETUPS]
      ${recentSetups.length > 0 ? recentSetups.map(s =>
            `- ${s.symbol} [${s.tradeType}]: ${s.setupType} Setup. Target: ${s.targetPct}%. Confidence: ${s.confidence}/100.`
        ).join('\n') : 'No high-confidence screened setups currently actively tracked.'}

      [RECENT TECHNICAL ALERTS]
      ${recentAlerts.length > 0 ? recentAlerts.map(a =>
            `- ${a.symbol} (${a.signalType}): ${JSON.stringify(a.signals)} | Close: ${a.closePrice}`
        ).join('\n') : 'No recent technical alerts found.'}

      [MACROECONOMIC NEWS]
      ${recentNews.length > 0 ? recentNews.map(n =>
            `- ${n.source}: ${n.title}`
        ).join('\n') : 'No recent news events found.'}

      User Query: "${query}"

      Task: Provide a concise, highly strategic answer. If the user asks for an options scalp, evaluate the risk based on the PCR and Smart Money positioning provided above. If technicals contradict the FII data, point out the trap.
    `;

        // ==========================================
        // 3. CALL LOCAL LLM API via OpenAI SDK
        // ==========================================
        const aiModel = process.env.AI_MODEL || 'llama3.2';

        const messages = history.map((msg: any) => ({
            role: msg.role === 'user' ? 'user' : 'assistant',
            content: msg.content,
        }));

        messages.unshift({ role: 'system', content: systemPrompt });

        llmPromptPreview = systemPrompt.substring(0, 500);

        const response = await openai.chat.completions.create({
            model: aiModel,
            messages: messages,
            temperature: 0.3,
            max_tokens: 500,
        });

        const responseText = response.choices[0]?.message?.content || "No response generated.";
        llmResponsePreview = responseText.substring(0, 500);

        const durationMs = Date.now() - runStartTime;

        // Log the agent run
        try {
            await db.insert(agentRuns).values({
                agentName: 'rag_copilot',
                runStatus: 'SUCCESS',
                durationMs,
                llmModel: aiModel,
                llmPromptTokens: response.usage?.prompt_tokens ?? null,
                llmCompletionTokens: response.usage?.completion_tokens ?? null,
                llmPromptPreview,
                llmResponsePreview,
                symbolProcessed: symbol || null,
                metadata: { query: query.substring(0, 200), alertsUsed: recentAlerts.length },
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
                agentName: 'rag_copilot',
                runStatus: 'FAILED',
                durationMs,
                llmModel: process.env.AI_MODEL || 'llama3.2',
                llmPromptPreview: llmPromptPreview || null,
                errorMessage: error.message?.substring(0, 1000),
            });
        } catch (logErr) {
            console.error('Failed to log agent run error:', logErr);
        }

        console.error('Chat API Error:', error);
        return NextResponse.json({ error: error.message || 'Failed to generate response' }, { status: 500 });
    }
}
