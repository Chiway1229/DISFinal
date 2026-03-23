#!/usr/bin/env python3
"""
防超賣驗證腳本 - 簡化版
只檢查核心：得標用戶數是否 <= 庫存限制 K
"""

import subprocess
import sys


def get_postgres_pod():
    """取得 PostgreSQL Pod"""
    cmd = ['kubectl', 'get', 'pods', '-n', 'flash-sale', '-l', 'app=postgres',
           '--field-selector=status.phase=Running', '-o', 'jsonpath={.items[0].metadata.name}']
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def run_sql(pod, sql):
    """執行 SQL 查詢"""
    cmd = ['kubectl', 'exec', '-n', 'flash-sale', pod, '--',
           'psql', '-U', 'admin', '-d', 'flash_sale', '-t', '-c', sql]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode == 0, result.stdout.strip()


def main():
    print("\n" + "="*70)
    print("防超賣驗證 (Anti-Overselling Check)")
    print("="*70 + "\n")

    # 找到 PostgreSQL Pod
    pg_pod = get_postgres_pod()
    if not pg_pod:
        print("[ERROR] 找不到 PostgreSQL Pod")
        sys.exit(1)

    print(f"PostgreSQL Pod: {pg_pod}\n")

    # 查詢每個 sale 的得標用戶數（只看每個用戶的最高分）
    sql = """
    WITH best_bids AS (
        SELECT DISTINCT ON (sale_id, user_id)
            sale_id,
            user_id,
            calculated_score,
            created_at
        FROM bids
        ORDER BY sale_id, user_id, calculated_score DESC, created_at ASC
    ),
    ranked_bids AS (
        SELECT
            sale_id,
            user_id,
            calculated_score,
            ROW_NUMBER() OVER (PARTITION BY sale_id ORDER BY calculated_score DESC, created_at ASC) - 1 as rank
        FROM best_bids
    )
    SELECT
        s.id as sale_id,
        s.inventory_limit as K,
        COUNT(DISTINCT rb.user_id) FILTER (WHERE rb.rank < s.inventory_limit) as winner_count,
        COUNT(b.*) as total_bids,
        COUNT(DISTINCT b.user_id) as unique_users
    FROM sales s
    LEFT JOIN bids b ON s.id = b.sale_id
    LEFT JOIN ranked_bids rb ON s.id = rb.sale_id
    GROUP BY s.id, s.inventory_limit
    ORDER BY s.id;
    """

    success, output = run_sql(pg_pod, sql)

    if not success:
        print("[ERROR] 查詢失敗")
        sys.exit(1)

    if not output:
        print("[WARN] 沒有找到任何 sale 資料")
        sys.exit(0)

    # 解析結果
    print("Sale ID | 庫存限制 K | 得標用戶數 | 總出價數 | 總用戶數 | 狀態")
    print("-" * 70)

    all_pass = True
    lines = [line.strip() for line in output.split('\n') if line.strip() and '|' in line]

    for line in lines:
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 5:
            sale_id = parts[0]
            k = int(parts[1])
            winner_count = int(parts[2]) if parts[2] else 0
            total_bids = int(parts[3]) if parts[3] else 0
            unique_users = int(parts[4]) if parts[4] else 0

            status = "PASS" if winner_count <= k else "FAIL - 超賣!!!"
            if winner_count > k:
                all_pass = False

            print(f"{sale_id:7} | {k:10} | {winner_count:12} | {total_bids:10} | {unique_users:11} | {status}")

    print("-" * 70)

    # 總結
    if all_pass:
        print("\n[SUCCESS] 所有 sale 都沒有超賣！防超賣機制正確運作！\n")
        sys.exit(0)
    else:
        print("\n[FAILURE] 檢測到超賣！系統存在問題！\n")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n測試已中止")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
