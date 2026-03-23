"""
WebSocket 路由 - 即時推播排行榜更新
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, Set
import json
import asyncio
from app.services.redis_service import get_redis_service, RedisService
from app.database import get_db
from sqlalchemy.orm import Session

router = APIRouter()

# 儲存所有 WebSocket 連接 {sale_id: Set[WebSocket]}
active_connections: Dict[int, Set[WebSocket]] = {}


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, sale_id: int):
        """新用戶連接"""
        await websocket.accept()
        if sale_id not in self.active_connections:
            self.active_connections[sale_id] = set()
        self.active_connections[sale_id].add(websocket)
        print(f"✅ WebSocket connected: sale_id={sale_id}, total={len(self.active_connections[sale_id])}")

    def disconnect(self, websocket: WebSocket, sale_id: int):
        """用戶斷開連接"""
        if sale_id in self.active_connections:
            self.active_connections[sale_id].discard(websocket)
            if not self.active_connections[sale_id]:
                del self.active_connections[sale_id]
        print(f"❌ WebSocket disconnected: sale_id={sale_id}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """發送個人訊息"""
        await websocket.send_text(message)

    async def broadcast(self, sale_id: int, message: str):
        """廣播訊息給所有連接該活動的用戶"""
        if sale_id not in self.active_connections:
            return

        disconnected = set()
        for connection in self.active_connections[sale_id]:
            try:
                await connection.send_text(message)
            except:
                disconnected.add(connection)

        # 清理斷開的連接
        self.active_connections[sale_id] -= disconnected


manager = ConnectionManager()


@router.websocket("/ws/{sale_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    sale_id: int
):
    """
    WebSocket 端點 - 即時推播排行榜

    連接: ws://localhost:8000/ws/{sale_id}

    訊息格式:
    {
        "type": "leaderboard_update",
        "sale_id": 1,
        "leaderboard": [
            {"rank": 1, "user_id": 123, "score": 900.5},
            ...
        ],
        "timestamp": "2025-12-03T14:30:00",
        "total_bids": 10
    }
    """
    await manager.connect(websocket, sale_id)

    try:
        # 發送初始排行榜
        from app.models.bid import Bid

        redis_service = RedisService()
        initial_leaderboard = redis_service.get_leaderboard(sale_id, limit=10)
        total_bids = redis_service.get_total_bids(sale_id)

        # 從資料庫查詢每個用戶的最高出價和取得活動資訊
        db = next(get_db())
        try:
            # 取得活動資訊（inventory_limit）
            from app.models.sale import Sale
            sale = db.query(Sale).filter(Sale.id == sale_id).first()
            inventory_limit = sale.inventory_limit if sale else 5

            for entry in initial_leaderboard:
                bid = db.query(Bid).filter(
                    Bid.sale_id == sale_id,
                    Bid.user_id == entry["user_id"]
                ).order_by(Bid.calculated_score.desc()).first()

                if bid:
                    entry["price"] = bid.price
                else:
                    entry["price"] = 0
        finally:
            db.close()

        # 計算最低得標門檻分數和最高出價
        min_winning_score = redis_service.get_min_winning_score(sale_id, inventory_limit)
        highest_price = redis_service.get_highest_price(sale_id)

        await manager.send_personal_message(
            json.dumps({
                "type": "init",
                "sale_id": sale_id,
                "leaderboard": initial_leaderboard,
                "total_bids": total_bids,
                "inventory_limit": inventory_limit,
                "min_winning_score": min_winning_score,
                "highest_price": highest_price,
                "message": "Connected to leaderboard updates"
            }),
            websocket
        )

        # 保持連接，處理心跳
        while True:
            data = await websocket.receive_text()

            # 處理心跳包
            if data == "ping":
                await manager.send_personal_message("pong", websocket)

            # 處理請求排行榜更新
            elif data == "refresh":
                leaderboard = redis_service.get_leaderboard(sale_id, limit=10)
                total_bids = redis_service.get_total_bids(sale_id)
                await manager.send_personal_message(
                    json.dumps({
                        "type": "leaderboard_update",
                        "sale_id": sale_id,
                        "leaderboard": leaderboard,
                        "total_bids": total_bids
                    }),
                    websocket
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, sale_id)


async def broadcast_leaderboard_update(sale_id: int):
    """
    廣播排行榜更新給所有連接的用戶

    當有新的出價時調用此函數
    """
    from app.models.bid import Bid
    from app.models.sale import Sale

    redis_service = RedisService()
    leaderboard = redis_service.get_leaderboard(sale_id, limit=10)
    total_bids = redis_service.get_total_bids(sale_id)

    # 從資料庫查詢每個用戶的最高出價和活動資訊
    db = next(get_db())
    try:
        # 取得活動資訊
        sale = db.query(Sale).filter(Sale.id == sale_id).first()
        inventory_limit = sale.inventory_limit if sale else 5

        for entry in leaderboard:
            bid = db.query(Bid).filter(
                Bid.sale_id == sale_id,
                Bid.user_id == entry["user_id"]
            ).order_by(Bid.calculated_score.desc()).first()

            if bid:
                entry["price"] = bid.price
            else:
                entry["price"] = 0
    finally:
        db.close()

    # 計算最低得標門檻分數和最高出價
    min_winning_score = redis_service.get_min_winning_score(sale_id, inventory_limit)
    highest_price = redis_service.get_highest_price(sale_id)

    message = json.dumps({
        "type": "leaderboard_update",
        "sale_id": sale_id,
        "leaderboard": leaderboard,
        "total_bids": total_bids,
        "inventory_limit": inventory_limit,
        "min_winning_score": min_winning_score,
        "highest_price": highest_price
    })

    await manager.broadcast(sale_id, message)
