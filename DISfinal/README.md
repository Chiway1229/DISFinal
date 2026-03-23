# 即時競標與限時搶購系統

Real-time Bidding & Flash Sale System - 高並發搶購平台

## 線上環境

| 服務 | URL |
|------|-----|
| API | http://34.81.236.6 |
| Frontend | http://35.189.162.209 |

## 核心特點

- **防超賣保證**: Redis Lua 腳本原子性操作，100% 防止超賣
- **高並發支援**: 500+ 並發用戶，100% 成功率
- **即時排行榜**: WebSocket 毫秒級推送
- **自動擴展**: Kubernetes HPA (3-30 pods)
- **雲原生**: GCP GKE 部署

## 評分公式

```
Score = α × P + β / (T + 1) + γ × W
```

- P: 出價金額
- T: 響應時間 (ms)
- W: 會員權重
- α, β, γ: 管理員設定的權重參數
- K: 庫存限制 (得標人數上限)

## 專案結構

```
DISfinal/
├── app/                    # FastAPI 後端
│   ├── models/             # 資料模型
│   ├── routers/            # API 路由
│   ├── schemas/            # Pydantic schemas
│   └── services/           # 業務邏輯
├── frontend/               # 前端 (HTML/JS)
├── k8s/                    # Kubernetes 配置
├── docs/                   # 文件
│   ├── SYSTEM_DOCUMENTATION.md  # 完整系統說明
│   ├── VERSION_HISTORY.md       # 版本修正紀錄
│   └── ...
├── load_test_gcp.py        # GCP 壓力測試
├── extreme_load_test.py    # 極限壓力測試
├── Dockerfile
└── docker-compose.yml
```

## 快速開始

### 本地開發

```bash
# 安裝依賴
uv sync

# 啟動服務
docker-compose up -d

# 初始化資料庫
python init_db.py

# 啟動應用
uvicorn app.main:app --reload
```

### GCP 部署

```bash
# 設置專案
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID

# 建立 GKE 叢集
make create-cluster

# 部署應用
make deploy
```

## 壓力測試

```bash
# 標準測試 (1000 用戶)
python load_test_gcp.py

# 極限測試 (7 種攻擊模式)
python extreme_load_test.py --mode nuclear --users 500 --duration 60
```

### 測試結果

| 模式 | 成功率 | Peak RPS | 防超賣 |
|------|--------|----------|--------|
| Berserker | 100% | 93 | ✅ |
| Tsunami | 100% | 133 | ✅ |
| Nuclear | 100% | 117 | ✅ |

## 文件

- [完整系統說明](docs/SYSTEM_DOCUMENTATION.md)
- [版本修正紀錄](docs/VERSION_HISTORY.md)
- [GCP 部署指南](docs/GCP_DEPLOYMENT_GUIDE.md)

## 技術棧

- **Backend**: FastAPI, SQLAlchemy, Pydantic
- **Database**: PostgreSQL
- **Cache**: Redis (Sorted Set + Lua Script)
- **Frontend**: HTML, JavaScript, WebSocket
- **Infrastructure**: Docker, Kubernetes, GCP GKE

---

*NTU DIS Final Project - 2024 Fall*
