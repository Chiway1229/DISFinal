"""
FastAPI 主程式 - 即時競標搶購系統
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers import auth, admin, bids, websocket

app = FastAPI(
    title="即時競標搶購系統",
    description="Real-time Bidding & Flash Sale System",
    version="1.0.0"
)

# CORS 設定 (允許前端跨域請求)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開發環境允許所有來源,生產環境應限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 註冊路由
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(bids.router)
app.include_router(websocket.router)

# 靜態文件服務 (前端頁面)
try:
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
except:
    pass  # 如果 frontend 目錄不存在，跳過


@app.get("/")
async def root():
    """根路徑"""
    return {
        "message": "即時競標搶購系統 API",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康檢查"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
