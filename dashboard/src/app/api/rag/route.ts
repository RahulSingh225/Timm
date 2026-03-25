import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/db/index';
import { marketAlerts, fiiDiiFlows, newsEvents, participantData } from '@/db/schema';
import { desc, eq, sql } from 'drizzle-orm';
import { GoogleGenerativeAI } from '@google/generative-ai';

// Initialize Gemini
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY || '');

export async function POST(req: NextRequest) {
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

        // Fetch the 5 most recent technical alerts (Filter by symbol if provided)
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

        // Fetch the latest FII/DII Cash & Derivative positioning
        const latestSmartMoney = await db.select()
            .from(fiiDiiFlows)
            .orderBy(desc(fiiDiiFlows.tradeDate))
            .limit(1);

        // Fetch granular participant data (Net indexing limits context, but good for precision)
        const recentParticipantData = await db.select()
            .from(participantData)
            .orderBy(desc(participantData.tradeDate))
            .limit(4);

        // Fetch the latest 3 macroeconomic news events
        const recentNews = await db.select()
            .from(newsEvents)
            .orderBy(desc(newsEvents.publishedAt))
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
      
      [GRANULAR PARTICIPANT NET OPTIONS (Contracts)]
      ${recentParticipantData.length > 0 ? recentParticipantData.map(p =>
            `- ${p.participantType}: Net Calls [${p.netIndexCall}], Net Puts [${p.netIndexPut}], Net IdxFut [${p.netIndexFutures}]`
        ).join('\n') : 'No granular options participant data available.'}

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
        // 3. CALL GEMINI API
        // ==========================================
        // Using 2.5-flash since you recently updated to it, or 2.5-pro for reasoning
        const model = genAI.getGenerativeModel({ model: 'gemini-2.5-flash' });

        // Create a chat session to maintain conversation history
        const chat = model.startChat({
            history: history.map((msg: any) => ({
                role: msg.role === 'user' ? 'user' : 'model',
                parts: [{ text: msg.content }],
            })),
        });

        const result = await chat.sendMessage(systemPrompt);
        const responseText = result.response.text();

        return NextResponse.json({ reply: responseText, response: responseText });

    } catch (error: any) {
        console.error('RAG API Error:', error);
        return NextResponse.json({ error: error.message || 'Failed to generate response' }, { status: 500 });
    }
}
