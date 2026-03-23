"""
Score 計算器

評分公式: Score = α·P + β/(T+1) + γ·W

其中:
- P: 出價價格 (price)
- T: 反應時間 (毫秒)
- W: 會員權重 (0.5-1.0)
- α, β, γ: 權重參數
"""


def calculate_score(
    price: float,           # P: 出價價格
    response_time_ms: int,  # T: 反應時間 (毫秒)
    weight: float,          # W: 會員權重 (0.5-1.0)
    alpha: float,           # α: 價格權重
    beta: float,            # β: 時間權重
    gamma: float            # γ: 會員權重
) -> float:
    """
    計算出價分數

    Args:
        price: 出價金額
        response_time_ms: 從活動開始到出價的時間 (毫秒)
        weight: 會員權重 (0.5-1.0)
        alpha: 價格權重 α
        beta: 時間權重 β
        gamma: 會員權重 γ

    Returns:
        計算出的分數 (保留 6 位小數)

    Example:
        >>> calculate_score(1500, 150, 0.75, 0.6, 0.3, 0.1)
        900.077  # 0.6*1500 + 0.3/(150+1) + 0.1*0.75
    """
    # Score = α·P + β/(T+1) + γ·W
    score = alpha * price + beta / (response_time_ms + 1) + gamma * weight

    # 保留 6 位小數
    return round(score, 6)
