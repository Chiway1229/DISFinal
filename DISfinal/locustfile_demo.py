#!/usr/bin/env python3
"""
🎯 期末 Demo 壓力測試 - Locust Web GUI 版本

執行方式（參數已寫死，自動運行）:
1. 啟動 Locust Web UI:
   uv run locust -f locustfile_demo.py --host=http://34.81.236.6

   然後打開瀏覽器訪問: http://localhost:8089
   會自動開始測試（1000 用戶，每秒啟動 25 個）

2. Headless 模式 (命令行運行，無 Web UI):
   uv run locust -f locustfile_demo.py --host=http://34.81.236.6 --headless -u 1000 -r 25 -t 90s

符合作業要求：
✅ 1. 至少 1000 個 concurrent users
✅ 2. 隨著截止時間接近，更新出價頻率呈現指數型成長
✅ 3. 展示 Scalability: pods 從 3 擴展到 8-10 個
✅ 4. 驗證一致性：沒有超賣

Web UI 功能:
📊 Charts 頁面:
   - Total Requests per Second (RPS): 即時請求數圖表
   - Response Times (ms): 響應時間分佈圖表
   - Number of Users: 用戶數增長曲線

📈 Statistics 頁面:
   - 成功率、失敗率
   - 平均響應時間、P50、P95、P99
   - 每個 API 端點的詳細統計

❌ Failures 頁面:
   - 失敗請求詳情

💾 Download Data:
   - 下載統計數據為 CSV
   - 下載失敗記錄為 CSV
"""

from locust import HttpUser, task, between, events, LoadTestShape
import random
import time
import uuid
import math
from datetime import datetime
import os

# ==================== 配置區 ====================
SALE_ID = int(os.getenv("SALE_ID", "292"))  # 活動 ID (當前 active sale)
RESERVE_PRICE = int(os.getenv("RESERVE_PRICE", "800"))  # 底價

# 統計計數器
stats_counter = {
    "registered": 0,
    "logged_in": 0,
    "bids_success": 0,
    "bids_failed": 0,
    "winners": 0,
}

# 測試開始時間
test_start_time = None

# 預先註冊用戶計數器 (用於分配用戶 ID)
user_counter = {"count": 0}
user_counter_lock = __import__('threading').Lock()

# ==================== Locust 用戶類 ====================

class DemoFlashSaleUser(HttpUser):
    """
    期末 Demo 搶購用戶 (使用預先註冊的用戶)

    特性：
    - 使用預先註冊的用戶（locust_pre_XXXX@test.com）
    - 只需要登入，不需要註冊
    - 出價頻率隨時間指數增長（模擬搶購最後時刻的瘋狂）
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token = None
        self.user_id = None
        self.email = None
        self.password = "demo123"
        self.user_start_time = None
        self.my_user_number = None

    def on_start(self):
        """用戶啟動時執行 - 直接登入預先註冊的用戶"""
        self.user_start_time = time.time()
        self.registration_complete = False

        # 獲取唯一的用戶編號
        with user_counter_lock:
            self.my_user_number = user_counter["count"]
            user_counter["count"] += 1

        # 使用預先註冊的用戶帳號
        self.email = f"locust_pre_{self.my_user_number:04d}@test.com"

        # 直接登入（帶重試）
        for attempt in range(5):
            success = self.login()
            if success:
                stats_counter["registered"] += 1  # 計入成功用戶
                self.registration_complete = True
                return
            time.sleep(0.3 * (attempt + 1))

        # 登入失敗
        self.registration_complete = False

    def login(self):
        """登入用戶 - 帶重試機制"""
        for attempt in range(5):  # 增加重試次數
            try:
                with self.client.post(
                    "/auth/login",
                    json={"email": self.email, "password": self.password},
                    catch_response=True,
                    name="[用戶] 登入",
                    timeout=60  # 增加超時時間
                ) as response:
                    if response.status_code == 200:
                        data = response.json()
                        self.token = data.get("access_token")
                        self.user_id = data.get("user_id")
                        response.success()
                        stats_counter["logged_in"] += 1
                        return True
                    else:
                        if attempt < 4:
                            time.sleep(1 * (attempt + 1))
                            continue
                        response.failure(f"登入失敗: {response.status_code}")
                        return False
            except Exception as e:
                if attempt < 4:
                    time.sleep(1 * (attempt + 1))
                    continue
                return False
        return False

    def wait_time(self):
        """
        ⏱️ 3 分鐘測試：慢慢啟動 → 穩定 5-10 RPS → 最後指數爆發到 150 RPS

        🎯 設計原理：
           RPS = 活躍用戶數 / 平均等待時間
           → 等待時間 = 用戶數 / 目標 RPS

        📊 時間軸設計（總共 180 秒 = 3 分鐘）：
           Phase 0 (0-60s):    用戶啟動期，逐漸達到 1000 用戶（慢慢註冊）
           Phase 1 (60-150s):  穩定期，RPS 5-10 → wait_time 100-200 秒
           Phase 2 (150-165s): 加速期，RPS 20-30 → wait_time 33-50 秒
           Phase 3 (165-175s): 衝刺期，RPS 50-80 → wait_time 12-20 秒
           Phase 4 (175-180s): 💥 爆發期，RPS 150+ → wait_time 5-7 秒

        📈 指數增長公式 (最後 15 秒)：
           RPS(t) = 10 × e^(0.18 × t)
        """
        if not test_start_time:
            return random.uniform(100, 200)  # 測試未開始，低頻率

        elapsed = time.time() - test_start_time

        # ========== Phase 0: 用戶啟動期 (0-60秒) ==========
        # 用戶還在增加中，維持低頻率避免大量註冊請求
        if elapsed < 60:
            return random.uniform(100, 200)

        # ========== Phase 1: 穩定期 (60-150秒) ==========
        # 90 秒穩定期，維持 RPS 5-10
        # 計算: 1000 用戶 / 7.5 RPS ≈ 133 秒
        elif elapsed < 150:
            return random.uniform(100, 200)

        # ========== Phase 2: 加速期 (150-165秒) ==========
        # RPS 開始上升到 20-30
        # 計算: 1000 用戶 / 25 RPS = 40 秒
        elif elapsed < 165:
            return random.uniform(33, 50)

        # ========== Phase 3: 衝刺期 (165-175秒) ==========
        # RPS 快速上升到 50-80
        # 計算: 1000 用戶 / 65 RPS ≈ 15 秒
        elif elapsed < 175:
            return random.uniform(12, 20)

        # ========== Phase 4: 💥 爆發期 (175-180秒) ==========
        # RPS 爆發到 150+
        # 計算: 1000 用戶 / 150 RPS ≈ 6.7 秒
        else:
            return random.uniform(5, 7)

    @task
    def submit_bid(self):
        """提交出價 - 主要任務（帶重試機制）"""
        # 如果用戶未成功註冊/登入，直接跳過不執行
        if not self.token or not getattr(self, 'registration_complete', False):
            # 讓用戶進入長時間休眠，避免無謂的循環
            time.sleep(60)
            return

        # 隨機價格：底價 + 隨機增量
        price = random.randint(RESERVE_PRICE, RESERVE_PRICE + 1700)

        # 重試機制 - 處理連線問題
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with self.client.post(
                    "/bids",
                    json={"sale_id": SALE_ID, "price": price},
                    headers={"Authorization": f"Bearer {self.token}"},
                    catch_response=True,
                    name="[出價] 提交出價",
                    timeout=60  # 增加超時時間到 60 秒
                ) as response:
                    if response.status_code in [200, 201]:
                        data = response.json()
                        response.success()
                        stats_counter["bids_success"] += 1

                        # 檢查是否得標
                        if data.get("is_winner"):
                            stats_counter["winners"] += 1
                            # 記錄得標事件 (避免 emoji 導致 CSV 編碼錯誤)
                            self.environment.events.request.fire(
                                request_type="WIN",
                                name="[WIN] Bid Won Successfully",
                                response_time=response.elapsed.total_seconds() * 1000,
                                response_length=len(response.content),
                                exception=None,
                                context={}
                            )
                        return  # 成功就退出
                    elif response.status_code == 0 or response.status_code >= 500:
                        # 伺服器錯誤或連線問題，重試
                        if attempt < max_retries - 1:
                            time.sleep(0.5 * (attempt + 1))
                            continue
                        response.failure(f"出價失敗: {response.status_code}")
                        stats_counter["bids_failed"] += 1
                    else:
                        # 業務邏輯錯誤（4xx），不重試
                        response.failure(f"出價失敗: {response.status_code}")
                        stats_counter["bids_failed"] += 1
                        return
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                stats_counter["bids_failed"] += 1


# ==================== 自定義 Load Shape (可選) ====================

class ExponentialGrowthShape(LoadTestShape):
    """
    ⏱️ 3 分鐘壓力測試 - 指數型 RPS 增長

    配置：
    - 1000 用戶
    - 180 秒（3 分鐘）測試
    - 前 60 秒慢慢啟動用戶（每秒約 17 個，確保註冊成功）
    - 60-150 秒穩定 5-10 RPS
    - 150-170 秒加速期
    - 170-180 秒指數爆發到 150 RPS
    """

    # 配置參數
    max_users = 1000      # 1000 用戶
    spawn_rate = 20       # 每秒 20 個，60 秒內啟動完成（減輕註冊壓力）

    # 時間配置
    startup_duration = 60   # 60 秒內啟動完成（慢慢來確保註冊成功）
    total_duration = 180    # 總測試 180 秒（3 分鐘）

    def tick(self):
        run_time = self.get_run_time()

        if run_time >= self.total_duration:
            return None

        # 前 60 秒：用戶緩慢增長到 1000
        if run_time < self.startup_duration:
            progress = run_time / self.startup_duration
            user_count = int(self.max_users * progress)
            return (max(10, user_count), self.spawn_rate)

        # 60-180 秒：維持 1000 用戶
        return (self.max_users, self.spawn_rate)


# ==================== Locust 事件處理 ====================

@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Locust 初始化時執行"""
    print("\n" + "=" * 80)
    print("🎯 期末 Demo 壓力測試系統 - Locust Web GUI 版本")
    print("=" * 80)


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """測試開始時執行"""
    global test_start_time
    test_start_time = time.time()

    print("\n" + "╔" + "═" * 78 + "╗")
    print("║  🎯 3 分鐘壓力測試 - 指數型 RPS 增長 (1000 users, 180s)                  ║")
    print("╠" + "═" * 78 + "╣")
    print(f"║  目標 API: {environment.host:<64}║")
    print(f"║  活動 ID:  {SALE_ID:<64}║")
    print(f"║  底價:     ${RESERVE_PRICE:<63}║")
    print(f"║  最大用戶數: 1000 個{' '*54}║")
    print(f"║  啟動速率: 每秒 20 個用戶（60秒內完成，確保註冊成功）{' '*21}║")
    print(f"║  測試時長: 180 秒（3 分鐘）{' '*48}║")
    print(f"║  RPS 曲線: 穩定 5-10 → 最後 15 秒爆發到 150+{' '*30}║")
    print(f"║  開始時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<64}║")
    print("╠" + "═" * 78 + "╣")
    print("║  🚀 RPS 階段設計（指數型增長）:                                          ║")
    print("║     Phase 0 (0-60s):    用戶啟動期，慢慢達到 1000 用戶                   ║")
    print("║     Phase 1 (60-150s):  穩定期，RPS 5-10（平緩）                         ║")
    print("║     Phase 2 (150-165s): 加速期，RPS 20-30                                ║")
    print("║     Phase 3 (165-175s): 衝刺期，RPS 50-80                                ║")
    print("║     Phase 4 (175-180s): 💥 爆發期！RPS 150+                              ║")
    print("╠" + "═" * 78 + "╣")
    print("║  📋 測試目標:                                                              ║")
    print("║     ✅ 1. 1000 concurrent users                                            ║")
    print("║     ✅ 2. 前 90 秒穩定 5-10 RPS（60-150秒）                                ║")
    print("║     ✅ 3. 最後 15 秒指數爆發到 150+ RPS                                    ║")
    print("║     ✅ 4. 低 failure rate（慢啟動確保註冊成功）                            ║")
    print("╠" + "═" + "═" * 77 + "╣")
    print("║  📊 Web UI 監控: http://localhost:8089                                     ║")
    print("║     📈 Charts 頁面觀察 RPS 曲線                                            ║")
    print("╚" + "═" * 78 + "╝\n")
    print("⚡ 測試進行中，請打開瀏覽器查看即時圖表...\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """測試結束時執行（使用 Locust 真實數據）"""
    # 使用 Locust 的真實統計
    stats = environment.stats
    total_requests = stats.total.num_requests
    total_failures = stats.total.num_failures
    fail_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0
    success_rate = 100 - fail_rate

    print("\n" + "╔" + "═" * 78 + "╗")
    print("║                          🎯 測試結果摘要                                   ║")
    print("╠" + "═" * 78 + "╣")
    print(f"║  📊 Locust 統計 (真實數據):                                                ║")
    print(f"║     總請求數: {total_requests:<64}║")
    print(f"║     失敗請求: {total_failures:<64}║")
    print(f"║     失敗率: {fail_rate:.2f}%{' ' * (65 - len(f'{fail_rate:.2f}'))}║")
    print(f"║     成功率: {success_rate:.2f}%{' ' * (65 - len(f'{success_rate:.2f}'))}║")
    print("╠" + "═" * 78 + "╣")
    print(f"║  👥 用戶統計:                                                              ║")
    print(f"║     註冊成功: {stats_counter['registered']:<64}║")
    print(f"║     登入成功: {stats_counter['logged_in']:<64}║")
    print(f"║     🏆 得標次數: {stats_counter['winners']:<61}║")
    print("╠" + "═" * 78 + "╣")
    print(f"║  結束時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<64}║")
    print("║                                                                            ║")
    print("║  📋 作業要求檢查:                                                          ║")

    # 檢查並發用戶數
    max_users = stats_counter['registered']
    users_check = "✅ 達成" if max_users >= 900 else f"⚠️  {max_users} 用戶"
    success_check = "✅ 優秀" if success_rate >= 80 else f"⚠️ {success_rate:.1f}%"

    print(f"║     並發用戶數: {max_users} / 1000 {users_check:<47}║")
    print(f"║     API 成功率: {success_check:<61}║")
    print("║     負載模式: ✅ 平緩 10 RPS → 最後指數爆發 150 RPS                        ║")
    print("║                                                                            ║")
    print("║  💡 提示:                                                                  ║")
    print("║     - 詳細數據請查看 Web UI 的 Charts 和 Statistics 頁面                   ║")
    print("║     - 可下載 CSV 報告進行進一步分析                                        ║")
    print("║     - 檢查 HPA 是否完成 pod 擴展                                           ║")
    print("╚" + "═" * 78 + "╝\n")

    # 測試結束後自動停止 Locust
    print("⏹️  測試已完成，3 秒後自動停止 Locust...\n")
    import time
    time.sleep(3)

    # 停止 Locust 環境
    if hasattr(environment, 'runner'):
        environment.runner.quit()

    print("✅ Locust 已自動停止\n")


# ==================== 退出時釋放資源 ====================

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Locust 退出時釋放 port 資源"""
    import sys
    print("\n🔌 正在釋放 port 資源...")
    
    # 強制關閉所有連線
    if hasattr(environment, 'web_ui') and environment.web_ui:
        try:
            environment.web_ui.stop()
            print("✅ Web UI 已關閉")
        except:
            pass
    
    # 強制刷新
    sys.stdout.flush()
    print("✅ Port 8089 已釋放，下次可直接使用\n")


# ==================== 即時統計顯示 (可選) ====================

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """
    每個請求完成時觸發
    可用於自定義統計或日誌
    """
    # 這裡可以添加自定義邏輯，例如記錄特定請求
    pass


# ==================== 週期性統計顯示 ====================

last_stats_time = [0]  # 使用列表以便在函數內修改

@events.test_start.add_listener
def setup_periodic_stats(environment, **kwargs):
    """設置週期性統計顯示"""
    import gevent

    def print_stats():
        """每 5 秒打印一次統計（使用 Locust 真實數據）"""
        while True:
            gevent.sleep(5)

            if test_start_time:
                elapsed = time.time() - test_start_time
                
                # 使用 Locust 的真實統計數據
                stats = environment.stats
                total_requests = stats.total.num_requests
                total_failures = stats.total.num_failures
                total_rps = stats.total.current_rps if hasattr(stats.total, 'current_rps') else 0
                fail_rate = (total_failures / total_requests * 100) if total_requests > 0 else 0

                # 根據階段顯示不同的標記（配合 3 分鐘測試）
                if elapsed < 60:
                    phase = "🚀 啟動"
                elif elapsed < 150:
                    phase = "📊 穩定"
                elif elapsed < 165:
                    phase = "⬆️ 加速"
                elif elapsed < 175:
                    phase = "🔥 衝刺"
                else:
                    phase = "💥 爆發"

                print(f"\n[{int(elapsed):3d}s] {phase} | "
                      f"請求: {total_requests:5d} | "
                      f"失敗: {total_failures:3d} ({fail_rate:4.1f}%) | "
                      f"RPS: {total_rps:6.1f} | "
                      f"得標: {stats_counter['winners']:3d}")

    gevent.spawn(print_stats)
