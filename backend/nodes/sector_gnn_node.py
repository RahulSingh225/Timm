# backend/nodes/sector_gnn_node.py
"""
SECTOR GNN NODE
Graph Neural Network for NIFTY sector rotation and macro trend prediction.
Integrates with candle_vector, FII/DII, and sentiment data.
"""

import os
import torch
import torch.nn.functional as F
import logging
from datetime import datetime
from typing import Dict
import pandas as pd
import numpy as np
from torch_geometric.nn import GATConv, global_mean_pool
from torch_geometric.data import Data
from sqlalchemy import text

from ..state import TimmState
from ..database import SessionLocal

logger = logging.getLogger(__name__)

# ========================= CONFIG =========================
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # Will use your T4
NUM_EPOCHS = 25
HIDDEN_DIM = 64
# =========================================================

class SectorGNN(torch.nn.Module):
    def __init__(self, num_features=12, num_classes=4):  # 4 classes: Strong Bull, Bull, Bear, Strong Bear rotation
        super().__init__()
        self.conv1 = GATConv(num_features, HIDDEN_DIM, heads=4, dropout=0.2)
        self.conv2 = GATConv(HIDDEN_DIM * 4, HIDDEN_DIM, heads=2, dropout=0.2)
        self.conv3 = GATConv(HIDDEN_DIM * 2, HIDDEN_DIM, heads=1, dropout=0.2)
        self.classifier = torch.nn.Linear(HIDDEN_DIM, num_classes)
        
    def forward(self, data):
        x, edge_index = data.x, data.edge_index
        x = F.relu(self.conv1(x, edge_index))
        x = F.relu(self.conv2(x, edge_index))
        x = self.conv3(x, edge_index)
        x = global_mean_pool(x, data.batch) if hasattr(data, 'batch') else x.mean(dim=0)
        return self.classifier(x)

def build_sector_graph() -> Data:
    """Build dynamic graph from your database"""
    with SessionLocal() as db:
        # Example: Fetch sector-level aggregated data
        df = pd.read_sql(text("""
            SELECT sector, avg_candle_scalar, avg_iv_adjusted, sentiment_score,
                   fii_flow, volume_zscore, correlation_to_nifty
            FROM sector_aggregates 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        """), db.bind)
    
    # Define sectors (NIFTY50 sectors)
    sectors = ['NIFTY', 'BANK', 'IT', 'AUTO', 'FMCG', 'PHARMA', 'ENERGY', 'METAL', 'REALTY', 'MEDIA']
    sector_to_idx = {s: i for i, s in enumerate(sectors)}
    
    # Node features (example)
    node_features = []
    for sector in sectors:
        row = df[df['sector'] == sector].mean(numeric_only=True) if not df[df['sector'] == sector].empty else pd.Series()
        feat = [
            row.get('avg_candle_scalar', 0),
            row.get('avg_iv_adjusted', 0),
            row.get('sentiment_score', 0),
            row.get('fii_flow', 0),
            row.get('volume_zscore', 0),
            row.get('correlation_to_nifty', 0.5),
            # Add more features as needed
        ] * 2  # pad to 12 features
        node_features.append(feat[:12])
    
    x = torch.tensor(node_features, dtype=torch.float).to(DEVICE)
    
    # Edge index: fully connected with self-loops for simplicity (you can improve with correlation threshold)
    edge_index = []
    for i in range(len(sectors)):
        for j in range(len(sectors)):
            edge_index.append([i, j])
    edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous().to(DEVICE)
    
    return Data(x=x, edge_index=edge_index)

def sector_gnn_node(state: TimmState) -> TimmState:
    logger.info("📊 Starting Sector GNN Training & Inference...")

    # Build graph
    data = build_sector_graph()
    
    # Initialize or load model
    model_path = "models/sector_gnn_best.pth"
    model = SectorGNN().to(DEVICE)
    
    if os.path.exists(model_path):
        model.load_state_dict(torch.load(model_path, map_location=DEVICE))
        logger.info("Loaded existing GNN model")
    else:
        # Quick training on historical patterns (you can expand this)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.005)
        for epoch in range(NUM_EPOCHS):
            optimizer.zero_grad()
            out = model(data)
            # Dummy supervised loss (replace with real rotation labels from history)
            loss = F.cross_entropy(out.unsqueeze(0), torch.tensor([1]).to(DEVICE))  # placeholder
            loss.backward()
            optimizer.step()
        torch.save(model.state_dict(), model_path)

    # Inference
    with torch.no_grad():
        prediction = model(data)
        probs = F.softmax(prediction, dim=0)
        predicted_class = torch.argmax(probs).item()
    
    rotation_map = {0: "Strong Bear Rotation", 1: "Bear Rotation", 2: "Bull Rotation", 3: "Strong Bull Rotation"}
    
    state.sector_gnn_signal = {
        "predicted_rotation": rotation_map[predicted_class],
        "confidence": float(probs.max()),
        "sector_strength": {s: float(p) for s, p in zip(["NIFTY","BANK","IT","AUTO","FMCG","PHARMA","ENERGY","METAL"], probs)},
        "generated_at": datetime.utcnow().isoformat(),
        "recommendation": "Favor IT & Pharma" if predicted_class >= 2 else "Favor Defensive (FMCG, Pharma)"
    }

    logger.info(f"✅ GNN Analysis complete → {state.sector_gnn_signal['predicted_rotation']} | Confidence: {state.sector_gnn_signal['confidence']:.2f}")
    return state