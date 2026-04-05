"""
OPTIONS CHAIN GNN NODE
Builds a Heterogeneous Graph over an Options Chain mapping 'call', 'put', and 'underlying' nodes.
Predicts local volatility direction across standard delta strikes.
"""

import os
import torch
import torch.nn.functional as F
from torch_geometric.nn import GATConv, HeteroConv
from torch_geometric.data import HeteroData
import logging
from datetime import datetime
import pandas as pd
import psycopg2

from langgraph_state import TradingState

logger = logging.getLogger(__name__)

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NUM_EPOCHS = 15
HIDDEN_DIM = 64
DB_URL = os.getenv("DATABASE_URL")

def _get_conn():
    return psycopg2.connect(DB_URL)

class OptionsIVGNN(torch.nn.Module):
    def __init__(self, hidden_dim=HIDDEN_DIM, num_heads=4):
        super().__init__()
        # Convolutions passing messages from underlying to options, and between adjacent strikes
        self.conv1 = HeteroConv({
            ('underlying', 'influences', 'call'): GATConv((-1, -1), hidden_dim, heads=num_heads, add_self_loops=False),
            ('underlying', 'influences', 'put'): GATConv((-1, -1), hidden_dim, heads=num_heads, add_self_loops=False),
            ('call', 'adjacency', 'call'): GATConv((-1, -1), hidden_dim, heads=1, add_self_loops=False),
            ('put', 'adjacency', 'put'): GATConv((-1, -1), hidden_dim, heads=1, add_self_loops=False),
        }, aggr='mean')
        
        self.conv2 = HeteroConv({
            ('underlying', 'influences', 'call'): GATConv((-1, -1), hidden_dim, heads=1, add_self_loops=False),
            ('underlying', 'influences', 'put'): GATConv((-1, -1), hidden_dim, heads=1, add_self_loops=False),
        }, aggr='mean')
        
        # Predicting IV shift direction (Binary: 0=Crush/Drop, 1=Expansion)
        self.call_classifier = torch.nn.Linear(hidden_dim, 2)
        self.put_classifier = torch.nn.Linear(hidden_dim, 2)

    def forward(self, data):
        x_dict = self.conv1(data.x_dict, data.edge_index_dict)
        x_dict = {key: F.relu(x) for key, x in x_dict.items() if x is not None}
        x_dict = self.conv2(x_dict, data.edge_index_dict)
        
        # Pull processed nodes out
        out_calls = self.call_classifier(x_dict['call'])
        out_puts = self.put_classifier(x_dict['put'])
        
        return out_calls, out_puts


def build_options_hetero_graph() -> HeteroData:
    """Mocking an Options Chain data structure"""
    
    # Normally we load Option Chain Greeks from PosgreSQL here
    # E.g. SELECT strike, delta, gamma, theta, vega, iv FROM options_chain WHERE symbol = 'NIFTY'
    NUM_STRIKES = 11  # e.g. 5 OTM, 1 ATM, 5 ITM
    
    data = HeteroData()
    
    # ── Node Features ──
    # [Delta, Gamma, Theta, Vega, Current IV]
    call_features = torch.rand((NUM_STRIKES, 5))
    put_features = torch.rand((NUM_STRIKES, 5))
    underlying_features = torch.tensor([[22450.0, 15.2, 0.45, 1.2, 850000.0]]) # Price, VIX, Return, Z-score, Vol
    
    data['call'].x = call_features.to(DEVICE)
    data['put'].x = put_features.to(DEVICE)
    data['underlying'].x = underlying_features.to(DEVICE)
    
    # ── Edges ──
    # Underlying dynamically influences all Calls and Puts
    u_to_c = torch.tensor([[0]*NUM_STRIKES, list(range(NUM_STRIKES))], dtype=torch.long)
    u_to_p = torch.tensor([[0]*NUM_STRIKES, list(range(NUM_STRIKES))], dtype=torch.long)
    
    data['underlying', 'influences', 'call'].edge_index = u_to_c.to(DEVICE)
    data['underlying', 'influences', 'put'].edge_index = u_to_p.to(DEVICE)
    
    # Strike Adjacency (contagion/spillover from strike 1 to strike 2)
    c_to_c = []
    p_to_p = []
    for i in range(NUM_STRIKES - 1):
        c_to_c.append([i, i+1])
        c_to_c.append([i+1, i])
        p_to_p.append([i, i+1])
        p_to_p.append([i+1, i])
        
    data['call', 'adjacency', 'call'].edge_index = torch.tensor(c_to_c, dtype=torch.long).t().contiguous().to(DEVICE)
    data['put', 'adjacency', 'put'].edge_index = torch.tensor(p_to_p, dtype=torch.long).t().contiguous().to(DEVICE)
    
    return data

def options_gnn_node(state: TradingState) -> TradingState:
    logger.info("📈 Processing Options Chain through IV HeteroGNN...")
    
    data = build_options_hetero_graph()
    model = OptionsIVGNN().to(DEVICE)
    
    model_path = "models/options_gnn_best.pth"
    if os.path.exists(model_path):
        model.load_state_dict(torch.load(model_path, map_location=DEVICE))
    else:
        # Dummy compile loop
        os.makedirs("models", exist_ok=True)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
        target_calls = torch.randint(0, 2, (11,)).to(DEVICE)
        target_puts = torch.randint(0, 2, (11,)).to(DEVICE)
        
        for _ in range(NUM_EPOCHS):
            optimizer.zero_grad()
            out_c, out_p = model(data)
            loss = F.cross_entropy(out_c, target_calls) + F.cross_entropy(out_p, target_puts)
            loss.backward()
            optimizer.step()
        torch.save(model.state_dict(), model_path)

    
    with torch.no_grad():
        out_c, out_p = model(data)
        call_probs = F.softmax(out_c, dim=1)
        put_probs = F.softmax(out_p, dim=1)
        
    # In a real environment, index 5 would be ATM
    atm_call_iv_expand = float(call_probs[5][1])
    atm_put_iv_expand = float(put_probs[5][1])
    
    # Generate Strategy Recommendations based on Volatility Surface prediction
    if atm_call_iv_expand > 0.6 and atm_put_iv_expand > 0.6:
        strategy = "LONG STRADDLE/STRANGLE"
        reason = "IV Expansion highly probable across ATM surface."
    elif atm_call_iv_expand < 0.4 and atm_put_iv_expand < 0.4:
        strategy = "SHORT IRON CONDOR"
        reason = "Volatility surface predicting structural crush inside adjacency wings."
    elif atm_call_iv_expand > 0.7:
        strategy = "BULL CALL SPREAD"
        reason = "NIFTY underlying flow skewing aggressive implied upside momentum."
    else:
        strategy = "BEAR PUT SPREAD"
        reason = "Option chain spillover accelerating downside delta positioning."

    state['options_gnn_signal'] = {
        "model_type": "THGNN_Options",
        "recommended_strategy": strategy,
        "reasoning": reason,
        "atm_call_iv_confidence": atm_call_iv_expand,
        "atm_put_iv_confidence": atm_put_iv_expand,
        "generated_at": datetime.utcnow().isoformat()
    }
    
    logger.info(f"✅ Options GNN Strategy: {strategy}")
    return state
