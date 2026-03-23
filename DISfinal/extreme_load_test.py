#!/usr/bin/env python3
"""
🔥 極限壓力測試腳本 - 瘋狂攻擊模式 🔥

模擬極端場景：
1. 海量並發用戶同時湧入
2. 瘋狂出價轟炸
3. 指數級流量爆發
4. 隨機價格戰
5. 波浪式攻擊
"""

import asyncio
import aiohttp
import random
import time
import argparse
import statistics
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import sys
import uuid

# 配置
API_URL = "http://34.81.236.6"

@dataclass
class AttackStats:
    """攻擊統計"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    register_success: int = 0
    register_failed: int = 0
    login_success: int = 0
    login_failed: int = 0
    bid_success: int = 0
    bid_failed: int = 0
    response_times: List[float] = field(default_factory=list)
    errors: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    rps_history: List[float] = field(default_factory=list)
    start_time: float = 0
    peak_rps: float = 0

stats = AttackStats()

async def register_user(session: aiohttp.ClientSession, user_id: int) -> Optional[tuple]:
    """註冊用戶 - 使用 UUID 確保高並發下的唯一性"""
    unique_id = uuid.uuid4().hex[:16]  # 16位隨機十六進制字串
    email = f"attacker_{user_id}_{unique_id}@attack.com"
    password = "attack123"

    try:
        async with session.post(
            f"{API_URL}/auth/register",
            json={"email": email, "password": password},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status in [200, 201]:
                stats.register_success += 1
                return email, password
            else:
                stats.register_failed += 1
                stats.errors[f"register_{response.status}"] += 1
                return None
    except Exception as e:
        stats.register_failed += 1
        stats.errors[f"register_error"] += 1
        return None

async def login_user(session: aiohttp.ClientSession, email: str, password: str) -> Optional[str]:
    """登入用戶"""
    for attempt in range(3):
        try:
            async with session.post(
                f"{API_URL}/auth/login",
                json={"email": email, "password": password},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    stats.login_success += 1
                    return data.get("access_token")
                else:
                    if attempt == 2:
                        stats.login_failed += 1
                        stats.errors[f"login_{response.status}"] += 1
        except Exception as e:
            if attempt == 2:
                stats.login_failed += 1
                stats.errors["login_error"] += 1
        await asyncio.sleep(0.2)
    return None

async def submit_bid(session: aiohttp.ClientSession, token: str, sale_id: int, price: float) -> bool:
    """提交出價"""
    start = time.time()
    try:
        async with session.post(
            f"{API_URL}/bids",
            json={"sale_id": sale_id, "price": price},
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            elapsed = (time.time() - start) * 1000
            stats.response_times.append(elapsed)
            stats.total_requests += 1

            if response.status == 200:
                stats.successful_requests += 1
                stats.bid_success += 1
                return True
            else:
                stats.failed_requests += 1
                stats.bid_failed += 1
                stats.errors[f"bid_{response.status}"] += 1
                return False
    except asyncio.TimeoutError:
        stats.failed_requests += 1
        stats.errors["timeout"] += 1
        return False
    except Exception as e:
        stats.failed_requests += 1
        stats.errors["connection_error"] += 1
        return False

async def berserker_attacker(session: aiohttp.ClientSession, attacker_id: int, sale_id: int,
                              reserve_price: float, duration: int, mode: str):
    """
    狂戰士攻擊者 - 瘋狂出價
    """
    # 註冊
    creds = await register_user(session, attacker_id)
    if not creds:
        return

    await asyncio.sleep(0.1)

    # 登入
    token = await login_user(session, creds[0], creds[1])
    if not token:
        return

    end_time = time.time() + duration
    bid_count = 0

    while time.time() < end_time:
        # 根據模式決定出價頻率和金額
        if mode == "berserker":
            # 狂戰士模式：固定高頻攻擊
            delay = random.uniform(0.05, 0.2)
            price = reserve_price + random.uniform(100, 10000)

        elif mode == "tsunami":
            # 海嘯模式：波浪式攻擊
            elapsed = time.time() - stats.start_time
            wave = (elapsed % 30) / 30  # 30秒一個波浪週期
            if wave < 0.5:
                delay = random.uniform(0.5, 1.0)  # 波谷
            else:
                delay = random.uniform(0.01, 0.05)  # 波峰
            price = reserve_price + random.uniform(500, 8000)

        elif mode == "sniper":
            # 狙擊手模式：精準高價出擊
            delay = random.uniform(0.3, 0.8)
            price = reserve_price + random.uniform(5000, 20000)

        elif mode == "machinegun":
            # 機槍模式：超高頻低價攻擊
            delay = random.uniform(0.01, 0.05)
            price = reserve_price + random.uniform(10, 500)

        elif mode == "chaos":
            # 混沌模式：完全隨機
            delay = random.uniform(0.01, 2.0)
            price = reserve_price + random.uniform(1, 50000)

        elif mode == "apocalypse":
            # 末日模式：指數級爆發
            elapsed = time.time() - stats.start_time
            progress = elapsed / duration
            # 指數級增長攻擊頻率
            base_delay = 1.0 * (0.01 ** progress)  # 從 1 秒到 0.01 秒
            delay = max(0.005, base_delay + random.uniform(-0.01, 0.01))
            price = reserve_price + random.uniform(100, 15000) * (1 + progress * 2)

        else:  # nuclear
            # 核彈模式：全力輸出
            delay = 0.001  # 幾乎無延遲
            price = reserve_price + random.uniform(1000, 30000)

        await submit_bid(session, token, sale_id, round(price, 2))
        bid_count += 1
        await asyncio.sleep(delay)

    return bid_count

async def rps_monitor(duration: int):
    """RPS 監控器"""
    stats.start_time = time.time()
    last_count = 0

    while time.time() - stats.start_time < duration + 30:
        await asyncio.sleep(1)
        current_count = stats.total_requests
        rps = current_count - last_count
        stats.rps_history.append(rps)
        if rps > stats.peak_rps:
            stats.peak_rps = rps
        last_count = current_count

        # 即時顯示
        elapsed = time.time() - stats.start_time
        success_rate = (stats.successful_requests / max(1, stats.total_requests)) * 100
        print(f"\r⚡ {elapsed:.0f}s | RPS: {rps:4d} | Peak: {stats.peak_rps:4d} | "
              f"Total: {stats.total_requests:6d} | Success: {success_rate:.1f}% | "
              f"Bids: {stats.bid_success}", end="", flush=True)

async def launch_attack(users: int, duration: int, sale_id: int, reserve_price: float, mode: str):
    """發動攻擊"""
    print(f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  🔥🔥🔥  極限壓力測試 - {mode.upper()} 模式  🔥🔥🔥
╠══════════════════════════════════════════════════════════════════════════════╣
║  攻擊目標: {API_URL:<58} ║
║  並發用戶: {users:<58} ║
║  持續時間: {duration} 秒{' ' * (54 - len(str(duration)))} ║
║  活動 ID:  {sale_id:<58} ║
║  攻擊模式: {mode:<58} ║
╚══════════════════════════════════════════════════════════════════════════════╝
""")

    # 模式說明
    mode_desc = {
        "berserker": "狂戰士 - 固定高頻瘋狂攻擊",
        "tsunami": "海嘯 - 30秒週期波浪式攻擊",
        "sniper": "狙擊手 - 精準高價出擊",
        "machinegun": "機槍 - 超高頻低價轟炸",
        "chaos": "混沌 - 完全隨機不可預測",
        "apocalypse": "末日 - 指數級流量爆發",
        "nuclear": "核彈 - 全力輸出無延遲"
    }
    print(f"📋 模式說明: {mode_desc.get(mode, '未知模式')}\n")

    connector = aiohttp.TCPConnector(
        limit=0,  # 無限連接
        limit_per_host=0,
        ttl_dns_cache=300,
        force_close=False,
        enable_cleanup_closed=True
    )

    timeout = aiohttp.ClientTimeout(total=120, connect=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # 啟動 RPS 監控
        monitor_task = asyncio.create_task(rps_monitor(duration))

        # 分批啟動攻擊者
        batch_size = 100
        tasks = []

        print("🚀 啟動攻擊者...")
        for i in range(0, users, batch_size):
            batch_end = min(i + batch_size, users)
            print(f"\r🚀 啟動攻擊者 {i+1} - {batch_end}", end="", flush=True)

            batch_tasks = [
                berserker_attacker(session, j, sale_id, reserve_price, duration, mode)
                for j in range(i, batch_end)
            ]
            tasks.extend(batch_tasks)
            await asyncio.sleep(0.3)

        print(f"\n\n💥 全面攻擊開始！{users} 個攻擊者同時出擊！\n")

        # 等待所有攻擊完成
        await asyncio.gather(*tasks, return_exceptions=True)

        # 停止監控
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

def print_results():
    """輸出結果"""
    print(f"""

╔══════════════════════════════════════════════════════════════════════════════╗
║                        🎯 攻擊結果報告                                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  👥 用戶統計                                                                  ║
║     註冊成功: {stats.register_success:<10} 註冊失敗: {stats.register_failed:<25} ║
║     登入成功: {stats.login_success:<10} 登入失敗: {stats.login_failed:<25} ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  📤 請求統計                                                                  ║
║     總請求數: {stats.total_requests:<56} ║
║     成功請求: {stats.successful_requests:<56} ║
║     失敗請求: {stats.failed_requests:<56} ║
║     成功率:   {(stats.successful_requests / max(1, stats.total_requests) * 100):.2f}%{' ' * 52} ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  💰 出價統計                                                                  ║
║     成功出價: {stats.bid_success:<56} ║
║     失敗出價: {stats.bid_failed:<56} ║
╠══════════════════════════════════════════════════════════════════════════════╣""")

    if stats.response_times:
        avg_rt = statistics.mean(stats.response_times)
        min_rt = min(stats.response_times)
        max_rt = max(stats.response_times)
        median_rt = statistics.median(stats.response_times)
        p95 = sorted(stats.response_times)[int(len(stats.response_times) * 0.95)] if len(stats.response_times) > 20 else max_rt
        p99 = sorted(stats.response_times)[int(len(stats.response_times) * 0.99)] if len(stats.response_times) > 100 else max_rt

        print(f"""║  ⏱️ 響應時間 (ms)                                                              ║
║     平均: {avg_rt:>10.2f}    最小: {min_rt:>10.2f}    最大: {max_rt:>10.2f}          ║
║     中位數: {median_rt:>8.2f}    P95: {p95:>10.2f}    P99: {p99:>10.2f}          ║
╠══════════════════════════════════════════════════════════════════════════════╣""")

    if stats.rps_history:
        avg_rps = statistics.mean(stats.rps_history) if stats.rps_history else 0
        print(f"""║  📈 吞吐量                                                                    ║
║     峰值 RPS: {stats.peak_rps:<10.0f} 平均 RPS: {avg_rps:<30.2f} ║
╠══════════════════════════════════════════════════════════════════════════════╣""")

    if stats.errors:
        print("║  ❌ 錯誤統計                                                                  ║")
        for error, count in sorted(stats.errors.items(), key=lambda x: -x[1])[:5]:
            print(f"║     {error}: {count:<55} ║")

    # 評估結果
    success_rate = (stats.successful_requests / max(1, stats.total_requests)) * 100

    print("╠══════════════════════════════════════════════════════════════════════════════╣")
    if success_rate >= 99:
        print("║  🏆 結果: 系統堅如磐石！完美抵禦攻擊！                                       ║")
    elif success_rate >= 95:
        print("║  ✅ 結果: 系統表現優秀！輕微波動但整體穩定                                   ║")
    elif success_rate >= 90:
        print("║  ⚠️  結果: 系統承受壓力，有一定錯誤率，建議優化                              ║")
    elif success_rate >= 80:
        print("║  🔶 結果: 系統勉強支撐，需要進一步擴展和優化                                 ║")
    else:
        print("║  💥 結果: 系統被擊潰！需要大幅優化架構                                       ║")

    print("╚══════════════════════════════════════════════════════════════════════════════╝")

async def verify_no_overselling(sale_id: int):
    """驗證防超賣"""
    print("\n🔍 驗證防超賣機制...")

    async with aiohttp.ClientSession() as session:
        # 獲取活動信息
        async with session.get(f"{API_URL}/admin/sales/{sale_id}") as response:
            if response.status == 200:
                sale = await response.json()
                inventory_limit = sale.get("inventory_limit", 0)
                print(f"   庫存限制 (K): {inventory_limit}")
            else:
                print("   ❌ 無法獲取活動信息")
                return

        # 獲取排行榜
        async with session.get(f"{API_URL}/bids/{sale_id}/leaderboard?limit=1000") as response:
            if response.status == 200:
                data = await response.json()
                leaderboard = data.get("leaderboard", [])
                total_bidders = len(leaderboard)
                winners = [e for e in leaderboard if e["rank"] <= inventory_limit]

                print(f"   總出價人數: {total_bidders}")
                print(f"   得標人數: {len(winners)}")

                if len(winners) <= inventory_limit:
                    print(f"   ✅ 防超賣驗證通過！得標人數 ({len(winners)}) ≤ 庫存限制 ({inventory_limit})")
                else:
                    print(f"   ❌ 警告：可能存在超賣！得標人數 ({len(winners)}) > 庫存限制 ({inventory_limit})")

async def create_test_sale() -> int:
    """創建測試活動"""
    async with aiohttp.ClientSession() as session:
        # 創建產品
        product_data = {
            "name": f"Extreme Test {int(time.time())}",
            "reserve_price": 1000,
            "description": "Extreme load test product",
            "initial_stock": 100
        }
        async with session.post(f"{API_URL}/admin/products", json=product_data) as resp:
            if resp.status in [200, 201]:
                product = await resp.json()
                product_id = product["id"]
            else:
                print("❌ 無法創建產品")
                return 0

        # 創建活動
        from datetime import datetime, timedelta
        start_time = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")
        end_time = (datetime.utcnow() + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")

        sale_data = {
            "product_id": product_id,
            "start_time": start_time,
            "end_time": end_time,
            "alpha": 0.95,
            "beta": 1000,
            "gamma": 0.05,
            "inventory_limit": 10
        }
        async with session.post(f"{API_URL}/admin/sales", json=sale_data) as resp:
            if resp.status in [200, 201]:
                sale = await resp.json()
                sale_id = sale["id"]
            else:
                print("❌ 無法創建活動")
                return 0

        # 啟動活動
        async with session.patch(f"{API_URL}/admin/sales/{sale_id}/start") as resp:
            if resp.status == 200:
                print(f"✅ 測試活動已創建並啟動: Sale ID = {sale_id}")
                return sale_id
            else:
                print("❌ 無法啟動活動")
                return 0

def main():
    parser = argparse.ArgumentParser(description="🔥 極限壓力測試腳本")
    parser.add_argument("--users", type=int, default=1000, help="並發用戶數 (預設: 1000)")
    parser.add_argument("--duration", type=int, default=120, help="持續時間秒 (預設: 120)")
    parser.add_argument("--sale-id", type=int, default=0, help="活動 ID (0=自動創建)")
    parser.add_argument("--reserve-price", type=float, default=1000, help="底價 (預設: 1000)")
    parser.add_argument("--mode", type=str, default="apocalypse",
                       choices=["berserker", "tsunami", "sniper", "machinegun", "chaos", "apocalypse", "nuclear"],
                       help="攻擊模式")
    parser.add_argument("--verify", action="store_true", help="測試後驗證防超賣")

    args = parser.parse_args()

    print("""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   🔥🔥🔥  極限壓力測試系統  🔥🔥🔥                           ║
    ║                                                               ║
    ║   ⚠️  警告：此腳本僅用於授權的壓力測試                       ║
    ║   請勿用於未經授權的系統攻擊                                 ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)

    # 自動創建活動
    if args.sale_id == 0:
        print("🔧 創建測試活動...")
        sale_id = asyncio.run(create_test_sale())
        if sale_id == 0:
            print("❌ 無法創建測試活動，退出")
            sys.exit(1)
    else:
        sale_id = args.sale_id

    # 發動攻擊
    asyncio.run(launch_attack(args.users, args.duration, sale_id, args.reserve_price, args.mode))

    # 輸出結果
    print_results()

    # 驗證防超賣
    if args.verify:
        asyncio.run(verify_no_overselling(sale_id))

if __name__ == "__main__":
    main()
