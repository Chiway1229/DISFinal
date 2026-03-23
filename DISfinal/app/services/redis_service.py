"""
Redis 服務 - 管理即時排行榜和原子性操作

使用 Redis ZSET 存儲排行榜，並通過 Lua 腳本確保原子性操作
"""
import redis
from typing import Tuple, List, Dict
from app.config import settings


class RedisService:
    def __init__(self):
        """初始化 Redis 連接 - 優化連接池配置"""
        self.redis = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=100,           # 最大連接數
            socket_timeout=10,             # Socket 超時
            socket_connect_timeout=10,     # 連接超時
            retry_on_timeout=True,         # 超時重試
            health_check_interval=30       # 健康檢查間隔
        )

    # ===== Lua 腳本: 原子性更新排行榜 =====
    UPDATE_LEADERBOARD_SCRIPT = """
    local leaderboard_key = KEYS[1]
    local user_id = ARGV[1]
    local score = tonumber(ARGV[2])
    local max_winners = tonumber(ARGV[3])

    -- 更新分數 (如果已存在會覆蓋，取最新的出價)
    redis.call('ZADD', leaderboard_key, score, user_id)

    -- 取得排名 (0-indexed, 從高分到低分)
    local rank = redis.call('ZREVRANK', leaderboard_key, user_id)

    -- 判斷是否得標 (排名 < max_winners)
    local is_winner = 0
    if rank < max_winners then
        is_winner = 1
    end

    return {is_winner, rank}
    """

    def update_leaderboard(
        self,
        sale_id: int,
        user_id: int,
        score: float,
        max_winners: int
    ) -> Tuple[bool, int]:
        """
        原子性更新排行榜

        Args:
            sale_id: 活動 ID
            user_id: 用戶 ID
            score: 計算出的分數
            max_winners: 最多得標人數 (K)

        Returns:
            (是否得標, 排名) - 排名從 0 開始

        Example:
            >>> redis_service.update_leaderboard(1, 123, 900.077, 5)
            (True, 2)  # 得標, 排名第 3 (0-indexed)
        """
        leaderboard_key = f"sale:{sale_id}:leaderboard"

        # 執行 Lua 腳本 (保證原子性)
        result = self.redis.eval(
            self.UPDATE_LEADERBOARD_SCRIPT,
            1,  # 1 個 KEY
            leaderboard_key,  # KEYS[1]
            user_id, score, max_winners  # ARGV[1], ARGV[2], ARGV[3]
        )

        is_winner = bool(result[0])
        rank = int(result[1])

        return is_winner, rank

    def get_leaderboard(self, sale_id: int, limit: int = 10) -> List[Dict]:
        """
        取得排行榜前 N 名

        Args:
            sale_id: 活動 ID
            limit: 返回前幾名 (預設 10)

        Returns:
            排行榜列表 [{"rank": 1, "user_id": 123, "score": 900.5}, ...]

        Example:
            >>> redis_service.get_leaderboard(1, 5)
            [
                {"rank": 1, "user_id": 456, "score": 920.5},
                {"rank": 2, "user_id": 123, "score": 900.077},
                ...
            ]
        """
        leaderboard_key = f"sale:{sale_id}:leaderboard"

        # ZREVRANGE: 從高分到低分取前 N 名 (withscores=True 返回分數)
        result = self.redis.zrevrange(
            leaderboard_key,
            0, limit - 1,
            withscores=True
        )

        leaderboard = []
        for i, (user_id, score) in enumerate(result):
            leaderboard.append({
                "rank": i + 1,  # 轉為 1-indexed
                "user_id": int(user_id),
                "score": float(score)
            })

        return leaderboard

    def init_sale_params(
        self,
        sale_id: int,
        alpha: float,
        beta: float,
        gamma: float,
        start_time_ms: int,
        inventory_limit: int
    ):
        """
        初始化活動參數到 Redis (用於快取)

        Args:
            sale_id: 活動 ID
            alpha, beta, gamma: 評分公式權重
            start_time_ms: 活動開始時間 (毫秒時間戳)
            inventory_limit: 庫存限制 (K)
        """
        params_key = f"sale:{sale_id}:params"

        self.redis.hset(params_key, mapping={
            "alpha": alpha,
            "beta": beta,
            "gamma": gamma,
            "start_time_ms": start_time_ms,
            "inventory_limit": inventory_limit
        })

    def get_sale_params(self, sale_id: int) -> Dict:
        """
        從 Redis 取得活動參數 (快取)

        Args:
            sale_id: 活動 ID

        Returns:
            活動參數 dict

        Example:
            >>> redis_service.get_sale_params(1)
            {
                "alpha": 0.6,
                "beta": 0.3,
                "gamma": 0.1,
                "start_time_ms": 1701612345000,
                "inventory_limit": 5
            }
        """
        params_key = f"sale:{sale_id}:params"
        params = self.redis.hgetall(params_key)

        if not params:
            return None

        return {
            "alpha": float(params["alpha"]),
            "beta": float(params["beta"]),
            "gamma": float(params["gamma"]),
            "start_time_ms": int(params["start_time_ms"]),
            "inventory_limit": int(params["inventory_limit"])
        }

    def clear_leaderboard(self, sale_id: int):
        """清空排行榜 (用於測試或重置活動)"""
        leaderboard_key = f"sale:{sale_id}:leaderboard"
        self.redis.delete(leaderboard_key)

    def get_total_bids(self, sale_id: int) -> int:
        """取得排行榜上的總出價數"""
        leaderboard_key = f"sale:{sale_id}:leaderboard"
        return self.redis.zcard(leaderboard_key)

    def get_min_winning_score(self, sale_id: int, inventory_limit: int) -> float:
        """
        取得最低得標門檻分數（第K名的分數，若不足K人則返回當前最低分數）

        Args:
            sale_id: 活動 ID
            inventory_limit: 得標名額 K

        Returns:
            最低得標分數，如果出價數 < K，則返回當前最低分數；否則返回第K名分數
        """
        leaderboard_key = f"sale:{sale_id}:leaderboard"

        # 先取得總出價數
        total_bids = self.redis.zcard(leaderboard_key)

        if total_bids == 0:
            return 0.0

        # 如果出價數少於名額，返回當前最低分數（最後一名）
        if total_bids < inventory_limit:
            result = self.redis.zrevrange(
                leaderboard_key,
                total_bids - 1,
                total_bids - 1,
                withscores=True
            )
        else:
            # 取得第 K 名的分數 (索引從 0 開始，所以是 inventory_limit - 1)
            result = self.redis.zrevrange(
                leaderboard_key,
                inventory_limit - 1,
                inventory_limit - 1,
                withscores=True
            )

        if result:
            return float(result[0][1])
        return 0.0

    def get_highest_score(self, sale_id: int) -> float:
        """
        取得最高分數

        Args:
            sale_id: 活動 ID

        Returns:
            最高分數，如果沒有出價則返回 0
        """
        leaderboard_key = f"sale:{sale_id}:leaderboard"

        # 取得分數最高的第一名
        result = self.redis.zrevrange(
            leaderboard_key,
            0, 0,
            withscores=True
        )

        if result:
            return float(result[0][1])
        return 0.0

    def get_highest_price(self, sale_id: int) -> float:
        """
        取得最高出價（從資料庫查詢）

        Args:
            sale_id: 活動 ID

        Returns:
            最高出價金額，如果沒有出價則返回 0
        """
        from app.database import get_db
        from app.models.bid import Bid

        db = next(get_db())
        try:
            max_bid = db.query(Bid).filter(
                Bid.sale_id == sale_id
            ).order_by(Bid.price.desc()).first()

            if max_bid:
                return float(max_bid.price)
            return 0.0
        finally:
            db.close()


# 建立全局 Redis 服務實例
redis_service = RedisService()


# FastAPI 依賴注入
def get_redis_service() -> RedisService:
    """FastAPI 依賴注入函數"""
    return redis_service
