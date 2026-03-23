# 即時競標與限時搶購系統 - 完整系統說明文件

## 1. 系統概述

本系統是一個高並發即時競標平台，專為處理「雙十一」、「黑色星期五」等大型搶購活動的「驚群效應」(Thundering Herd Problem) 而設計。

### 1.1 核心特點

- **防超賣保證**: 使用 Redis Lua 腳本實現原子性操作，100% 防止超賣
- **高並發支援**: 經壓力測試驗證可處理 500+ 並發用戶，100% 成功率
- **即時排行榜**: WebSocket 推送即時更新，毫秒級響應
- **自動擴展**: Kubernetes HPA 根據 CPU/Memory 自動擴展 (3-30 pods)
- **雲原生架構**: 完整容器化，部署於 Google Cloud Platform GKE

### 1.2 線上環境

| 服務 | URL |
|------|-----|
| API | http://34.81.236.6 |
| Frontend | http://35.189.162.209 |

---

## 2. 系統架構

```
┌─────────────────────────────────────────────────────────────────┐
│                         用戶端                                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Web 前端   │  │  Mobile App │  │  API Client │              │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘              │
└─────────┼────────────────┼────────────────┼─────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GCP Load Balancer                             │
└─────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Kubernetes (GKE)                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  Flash-Sale API (3-30 pods)              │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐     ┌─────────┐    │    │
│  │  │  Pod 1  │ │  Pod 2  │ │  Pod 3  │ ... │  Pod N  │    │    │
│  │  │ FastAPI │ │ FastAPI │ │ FastAPI │     │ FastAPI │    │    │
│  │  └────┬────┘ └────┬────┘ └────┬────┘     └────┬────┘    │    │
│  └───────┼───────────┼───────────┼───────────────┼─────────┘    │
│          │           │           │               │               │
│          ▼           ▼           ▼               ▼               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                     Redis (排行榜 + 快取)                  │  │
│  │  • Sorted Set: 即時排行榜                                  │  │
│  │  • Lua Script: 原子性防超賣                                │  │
│  │  • Cache: Sale/Product 資訊快取                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│          │                                                       │
│          ▼                                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   PostgreSQL (持久化)                      │  │
│  │  • Users: 用戶資料                                         │  │
│  │  • Products: 商品資料                                      │  │
│  │  • Sales: 搶購活動                                         │  │
│  │  • Bids: 出價紀錄                                          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心業務邏輯

### 3.1 評分公式

得標者由綜合評分決定，而非單純出價金額：

```
Score = α × P + β / (T + 1) + γ × W
```

| 參數 | 說明 | 範圍 |
|------|------|------|
| **P** (Price) | 用戶出價金額 | >= 底價 |
| **T** (Time) | 從活動開始的響應時間 (毫秒) | >= 0 |
| **W** (Weight) | 會員權重/貢獻度 | 1.0 - 5.0 |
| **α** | 價格權重係數 | 管理員設定 |
| **β** | 時間權重係數 | 管理員設定 |
| **γ** | 會員權重係數 | 管理員設定 |
| **K** | 庫存限制 (最多得標人數) | 管理員設定 |

### 3.2 防超賣機制

使用 Redis Lua 腳本實現原子性操作：

```lua
-- Redis Lua Script (簡化版)
local leaderboard_key = KEYS[1]
local max_winners = tonumber(ARGV[3])

-- 更新用戶分數
redis.call('ZADD', leaderboard_key, score, user_id)

-- 取得用戶排名 (0-indexed)
local rank = redis.call('ZREVRANK', leaderboard_key, user_id)

-- 判斷是否得標
local is_winner = (rank < max_winners) and 1 or 0

return {is_winner, rank}
```

**保證**: 無論多少並發請求，排行榜前 K 名永遠精確為 K 人。

---

## 4. API 端點

### 4.1 認證 API

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/auth/register` | 用戶註冊 |
| POST | `/auth/login` | 用戶登入，返回 JWT token |

### 4.2 出價 API

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/bids` | 提交出價 (需 JWT) |
| GET | `/bids/{sale_id}/leaderboard` | 取得排行榜 |

### 4.3 管理 API

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/admin/products` | 取得商品列表 |
| POST | `/admin/products` | 創建商品 |
| GET | `/admin/sales` | 取得活動列表 |
| POST | `/admin/sales` | 創建搶購活動 |
| PUT | `/admin/sales/{id}/activate` | 啟動活動 |
| PUT | `/admin/sales/{id}/complete` | 結束活動 |

### 4.4 WebSocket

| 端點 | 說明 |
|------|------|
| `ws://.../ws/{sale_id}` | 即時排行榜更新推送 |

---

## 5. 資料庫設計

### 5.1 ER Diagram

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│   users     │       │  products   │       │   sales     │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id (PK)     │       │ id (PK)     │       │ id (PK)     │
│ email       │       │ name        │       │ product_id  │──┐
│ password    │       │ description │       │ start_time  │  │
│ weight      │       │ reserve_price│      │ end_time    │  │
│ created_at  │       │ image_url   │       │ alpha       │  │
└──────┬──────┘       │ created_at  │       │ beta        │  │
       │              └──────┬──────┘       │ gamma       │  │
       │                     │              │ inventory_limit│ │
       │                     │              │ status      │  │
       │                     │              └──────┬──────┘  │
       │                     │                     │         │
       │              ┌──────┴─────────────────────┘         │
       │              │                                      │
       ▼              ▼                                      │
┌─────────────────────────────┐                              │
│          bids               │◄─────────────────────────────┘
├─────────────────────────────┤
│ id (PK)                     │
│ user_id (FK)                │
│ product_id (FK)             │
│ sale_id (FK)                │
│ price                       │
│ response_time_ms            │
│ calculated_score            │
│ rank                        │
│ is_winner                   │
│ created_at                  │
└─────────────────────────────┘
```

---

## 6. 專案結構

```
DISfinal/
├── app/                          # 後端應用程式
│   ├── __init__.py
│   ├── main.py                   # FastAPI 主入口
│   ├── config.py                 # 配置管理
│   ├── database.py               # 資料庫連接
│   ├── models/                   # SQLAlchemy 模型
│   │   ├── user.py
│   │   ├── product.py
│   │   ├── sale.py
│   │   └── bid.py
│   ├── routers/                  # API 路由
│   │   ├── auth.py               # 認證路由
│   │   ├── bids.py               # 出價路由 (核心)
│   │   ├── admin.py              # 管理路由
│   │   └── websocket.py          # WebSocket 路由
│   ├── schemas/                  # Pydantic 模型
│   │   └── __init__.py
│   └── services/                 # 業務邏輯服務
│       ├── auth_service.py       # JWT 認證
│       ├── redis_service.py      # Redis 操作
│       └── score_calculator.py   # 評分計算
│
├── frontend/                     # 前端應用
│   ├── index.html                # 用戶介面
│   └── admin.html                # 管理介面
│
├── k8s/                          # Kubernetes 配置
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secrets.yaml
│   ├── postgres-deployment.yaml
│   ├── redis-deployment.yaml
│   ├── api-deployment.yaml
│   ├── frontend-deployment.yaml
│   └── hpa.yaml                  # 自動擴展配置
│
├── docs/                         # 文件
│   ├── SYSTEM_DOCUMENTATION.md   # 本文件
│   ├── VERSION_HISTORY.md        # 版本修正紀錄
│   ├── GCP_DEPLOYMENT_GUIDE.md   # GCP 部署指南
│   └── ...
│
├── Dockerfile                    # Docker 映像檔
├── docker-compose.yml            # 本地開發環境
├── Makefile                      # 常用命令
├── load_test_gcp.py              # GCP 壓力測試
├── extreme_load_test.py          # 極限壓力測試
└── README.md                     # 專案說明
```

---

## 7. 部署架構

### 7.1 GKE 配置

| 組件 | 配置 |
|------|------|
| **Cluster** | GKE Standard, asia-east1 |
| **Node Pool** | e2-standard-4 (4 vCPU, 16GB RAM) |
| **API Pods** | 3-30 replicas (HPA) |
| **PostgreSQL** | 1 replica, 2 vCPU, 2GB RAM |
| **Redis** | 1 replica |

### 7.2 HPA (自動擴展)

```yaml
spec:
  minReplicas: 3
  maxReplicas: 30
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 70
```

---

## 8. 效能優化

### 8.1 Redis 快取策略

| 快取項目 | TTL | 用途 |
|----------|-----|------|
| `sale_cache:{id}` | 60秒 | 減少 Sale 資料庫查詢 |
| `product_cache:{id}` | 300秒 | 減少 Product 資料庫查詢 |
| `leaderboard:{sale_id}` | 永久 | 即時排行榜 (Sorted Set) |

### 8.2 資料庫連接池

```python
engine = create_engine(
    DATABASE_URL,
    pool_size=5,          # 每 Pod 基礎連接數
    max_overflow=10,      # 溢出連接數
    pool_timeout=10,      # 快速失敗重試
    pool_recycle=300,     # 5 分鐘回收
)
```

### 8.3 PostgreSQL 優化

```
max_connections=1000
shared_buffers=512MB
work_mem=16MB
effective_cache_size=1GB
```

---

## 9. 壓力測試結果

### 9.1 測試模式

| 模式 | 說明 | 成功率 | Peak RPS |
|------|------|--------|----------|
| Berserker | 固定高頻攻擊 | 100% | 93 |
| Tsunami | 波浪式攻擊 | 100% | 133 |
| Nuclear | 全力輸出 | 100% | 117 |
| Apocalypse | 指數級爆發 | 100% | 121 |
| Chaos | 隨機模式 | 100% | 125 |

### 9.2 防超賣驗證

所有測試中，K=10 的活動**精確**產生 10 個得標者，防超賣機制 100% 有效。

---

## 10. 安全性

### 10.1 認證機制

- JWT Token 認證
- Token 有效期: 24 小時
- 密碼: bcrypt 雜湊加密

### 10.2 防護措施

- CORS 配置
- SQL Injection 防護 (SQLAlchemy ORM)
- 輸入驗證 (Pydantic)

---

## 11. 監控與日誌

### 11.1 健康檢查

```bash
# API 健康檢查
curl http://34.81.236.6/health
# 預期回應: {"status":"healthy"}
```

### 11.2 Kubernetes 監控

```bash
# 查看 Pod 狀態
kubectl get pods -n flash-sale

# 查看 HPA 狀態
kubectl get hpa -n flash-sale

# 查看 Pod 日誌
kubectl logs -f deployment/flash-sale-api -n flash-sale
```

---

## 12. 快速開始

### 12.1 本地開發

```bash
# 1. 安裝依賴
uv sync

# 2. 啟動 PostgreSQL 和 Redis
docker-compose up -d

# 3. 初始化資料庫
python init_db.py

# 4. 啟動應用
uvicorn app.main:app --reload
```

### 12.2 GCP 部署

```bash
# 1. 設置 GCP 專案
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# 2. 建立 GKE 叢集
make create-cluster

# 3. 部署應用
make deploy

# 4. 驗證部署
make verify
```

---

## 13. 聯絡資訊

- **課程**: 分散式系統 (Distributed Systems)
- **學期**: 2024 Fall
- **截止日期**: 2024/12/10

---

*本文件由 Claude Code 協助生成*
