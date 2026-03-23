// API 基礎 URL
// 本地開發: http://localhost:8000
// GCP 生產環境: http://34.81.236.6
const API_URL = 'http://34.81.236.6';
const WS_URL = 'ws://34.81.236.6';

// 全局變數
let currentToken = null;
let currentUserId = null;
let currentUserWeight = null;
let websocket = null;
let updateCount = 0;

// ===== 認證相關 =====

async function register() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    if (!email || !password) {
        showAuthStatus('請輸入 Email 和密碼', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/auth/register`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, password})
        });

        const data = await response.json();

        if (response.ok) {
            showAuthStatus(`✅ 註冊成功！會員權重: ${data.weight.toFixed(3)}`, 'success');
        } else {
            showAuthStatus(`❌ ${data.detail}`, 'error');
        }
    } catch (error) {
        showAuthStatus(`❌ 註冊失敗: ${error.message}`, 'error');
    }
}

async function login() {
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;

    if (!email || !password) {
        showAuthStatus('請輸入 Email 和密碼', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, password})
        });

        const data = await response.json();

        if (response.ok) {
            currentToken = data.access_token;
            currentUserId = data.user_id;
            currentUserWeight = data.weight;

            showAuthStatus('✅ 登入成功！', 'success');
            showUserInfo(email, data.user_id, data.weight);
            document.getElementById('bidCard').style.display = 'block';

            // 載入活動下拉選單
            loadSalesDropdown();
        } else {
            showAuthStatus(`❌ ${data.detail}`, 'error');
        }
    } catch (error) {
        showAuthStatus(`❌ 登入失敗: ${error.message}`, 'error');
    }
}

function showAuthStatus(message, type) {
    const statusDiv = document.getElementById('authStatus');
    statusDiv.innerHTML = `<div class="status ${type}">${message}</div>`;
}

function showUserInfo(email, userId, weight) {
    document.getElementById('userInfoCard').style.display = 'block';
    document.getElementById('userEmail').textContent = email;
    document.getElementById('userId').textContent = userId;
    document.getElementById('userWeight').textContent = weight.toFixed(3);
}

// ===== 出價相關 =====

async function loadSalesDropdown() {
    const saleSelect = document.getElementById('saleId');
    const leaderboardSelect = document.getElementById('leaderboardSaleId');

    try {
        const response = await fetch(`${API_URL}/admin/sales`);
        const sales = await response.json();

        if (response.ok) {
            // 清空現有選項
            saleSelect.innerHTML = '';

            // 過濾出 active 的活動，並按 ID 排序
            const activeSales = sales
                .filter(sale => sale.status === 'active')
                .sort((a, b) => a.id - b.id);

            if (activeSales.length === 0) {
                saleSelect.innerHTML = '<option value="">目前沒有進行中的活動</option>';
                return;
            }

            // 加入所有 active 活動到出價區選單
            activeSales.forEach(sale => {
                const option = document.createElement('option');
                option.value = sale.id;
                option.textContent = `活動 ${sale.id} - ${sale.product_name}`;
                saleSelect.appendChild(option);
            });

            // 自動選擇第一個活動
            if (activeSales.length > 0) {
                saleSelect.value = activeSales[0].id;
                loadSaleInfo();
            }

            // 同步更新排行榜下拉選單
            loadLeaderboardSalesDropdown();
        }
    } catch (error) {
        console.error('載入活動列表失敗:', error);
        saleSelect.innerHTML = '<option value="">載入失敗</option>';
    }
}

async function loadSaleInfo() {
    const saleId = document.getElementById('saleId').value;

    if (!saleId) {
        return;
    }

    try {
        const response = await fetch(`${API_URL}/admin/sales/${saleId}`);
        const sale = await response.json();

        if (response.ok) {
            // 更新 inventory_limit 顯示
            document.getElementById('inventoryLimit').textContent = sale.inventory_limit;

            // 設定出價金額的預設值為該活動的底價
            const bidPriceInput = document.getElementById('bidPrice');
            if (bidPriceInput && sale.reserve_price) {
                bidPriceInput.value = sale.reserve_price;
                bidPriceInput.placeholder = `最低 ${sale.reserve_price}`;
            }
        }
    } catch (error) {
        console.error('載入活動信息失敗:', error);
    }
}

async function submitBid() {
    if (!currentToken) {
        showBidResult('請先登入！', 'error');
        return;
    }

    const saleId = parseInt(document.getElementById('saleId').value);
    const price = parseFloat(document.getElementById('bidPrice').value);

    if (!price || price <= 0) {
        showBidResult('請輸入有效的出價金額', 'error');
        return;
    }

    const button = document.getElementById('bidButton');
    button.disabled = true;
    button.innerHTML = '<span class="loading"></span> 提交中...';

    try {
        const response = await fetch(`${API_URL}/bids`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentToken}`
            },
            body: JSON.stringify({sale_id: saleId, price})
        });

        const data = await response.json();

        if (response.ok) {
            const winnerIcon = data.is_winner ? '🎉' : '😢';
            const winnerText = data.is_winner ? '得標' : '未得標';
            showBidResult(
                `${winnerIcon} 出價成功！
                <br>分數: <strong>${data.score.toFixed(2)}</strong>
                <br>當前排名: <strong>#${data.rank}</strong>
                <br>反應時間: <strong>${data.response_time_ms}ms</strong>
                <br>狀態: <strong>${winnerText}</strong>
                <br><small style="color: #666;">${data.message}</small>`,
                'success'
            );
        } else {
            showBidResult(`❌ ${data.detail}`, 'error');
        }
    } catch (error) {
        showBidResult(`❌ 出價失敗: ${error.message}`, 'error');
    } finally {
        button.disabled = false;
        button.innerHTML = '🚀 立即出價';
    }
}

function showBidResult(message, type) {
    const resultDiv = document.getElementById('bidResult');
    resultDiv.innerHTML = `<div class="bid-result ${type}">${message}</div>`;
}

// ===== WebSocket 相關 =====

function connectWebSocket() {
    // 優先使用排行榜的選單，如果沒有則使用出價區的選單
    const leaderboardSaleId = document.getElementById('leaderboardSaleId').value;
    const bidSaleId = document.getElementById('saleId').value;
    const saleId = leaderboardSaleId || bidSaleId;

    if (!saleId) {
        console.log('沒有可用的活動 ID');
        return;
    }

    if (websocket) {
        console.log('WebSocket 已連接');
        return;
    }

    websocket = new WebSocket(`${WS_URL}/ws/${saleId}`);

    websocket.onopen = () => {
        console.log('✅ WebSocket 已連接');
        updateWSStatus('connected');
        document.getElementById('wsConnectBtn').style.display = 'none';
        document.getElementById('wsDisconnectBtn').style.display = 'inline-block';

        // 啟動心跳
        startHeartbeat();
    };

    websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('📨 收到訊息:', data);

        if (data.type === 'init') {
            console.log('🎯 初始化排行榜');
            updateLeaderboard(data);
        } else if (data.type === 'leaderboard_update') {
            console.log('🔄 排行榜更新');
            updateLeaderboard(data);
            updateCount++;

            // 動畫效果
            const leaderboardCard = document.querySelector('.leaderboard');
            leaderboardCard.style.animation = 'none';
            setTimeout(() => {
                leaderboardCard.style.animation = 'slideIn 0.5s ease-out';
            }, 10);
        }
    };

    websocket.onclose = () => {
        console.log('❌ WebSocket 已斷開');
        updateWSStatus('disconnected');
        websocket = null;
        document.getElementById('wsConnectBtn').style.display = 'inline-block';
        document.getElementById('wsDisconnectBtn').style.display = 'none';
        stopHeartbeat();
    };

    websocket.onerror = (error) => {
        console.error('❌ WebSocket 錯誤:', error);
        updateWSStatus('disconnected');
    };
}

function disconnectWebSocket() {
    if (websocket) {
        websocket.close();
        websocket = null;
    }
}

function updateWSStatus(status) {
    const statusDiv = document.getElementById('wsStatus');
    if (status === 'connected') {
        statusDiv.className = 'ws-status connected';
        statusDiv.textContent = '✅ 即時連線中';
    } else {
        statusDiv.className = 'ws-status disconnected';
        statusDiv.textContent = '❌ 未連接';
    }
}

// 心跳機制
let heartbeatInterval = null;

function startHeartbeat() {
    heartbeatInterval = setInterval(() => {
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send('ping');
        }
    }, 5000);
}

function stopHeartbeat() {
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }
}

// ===== 排行榜更新 =====

function updateLeaderboard(data) {
    const leaderboard = data.leaderboard;
    const totalBids = data.total_bids;
    const inventoryLimit = data.inventory_limit || 5;
    const minWinningScore = data.min_winning_score || 0;
    const highestPrice = data.highest_price || 0;

    const tbody = document.getElementById('leaderboardBody');
    tbody.innerHTML = '';

    // 更新統計資料
    document.getElementById('totalBids').textContent = totalBids || leaderboard.length;
    document.getElementById('inventoryLimit').textContent = inventoryLimit;
    document.getElementById('highestPrice').textContent = highestPrice.toFixed(0);

    // 如果總出價數少於得標名額，顯示 "-"
    if (totalBids < inventoryLimit) {
        document.getElementById('minWinningScore').textContent = '-';
    } else {
        document.getElementById('minWinningScore').textContent = minWinningScore.toFixed(2);
    }

    if (leaderboard.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; color: #999;">
                    目前沒有出價記錄
                </td>
            </tr>
        `;
        return;
    }

    // 只顯示得標者（前 K 名）
    const winners = leaderboard.filter(entry => entry.rank <= inventoryLimit);

    if (winners.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; color: #999;">
                    目前沒有得標者
                </td>
            </tr>
        `;
        return;
    }

    winners.forEach((entry, index) => {
        const row = tbody.insertRow();

        row.innerHTML = `
            <td>
                <span class="rank winner">
                    ${entry.rank <= 3 ? ['🥇', '🥈', '🥉'][entry.rank - 1] : `#${entry.rank}`}
                </span>
            </td>
            <td>
                User ${entry.user_id}
                ${entry.user_id === currentUserId ? ' <strong>(你)</strong>' : ''}
            </td>
            <td><strong>$${entry.price ? entry.price.toFixed(0) : '0'}</strong></td>
            <td><span style="color: #666;">${entry.score ? entry.score.toFixed(2) : '0.00'}</span></td>
        `;

        // 高亮顯示當前用戶
        if (entry.user_id === currentUserId) {
            row.style.background = '#fff3cd';
        }
    });
}

// ===== 排行榜商品選擇 =====

async function loadLeaderboardSalesDropdown() {
    const leaderboardSelect = document.getElementById('leaderboardSaleId');

    try {
        const response = await fetch(`${API_URL}/admin/sales`);
        const sales = await response.json();

        if (response.ok) {
            // 清空現有選項
            leaderboardSelect.innerHTML = '';

            // 過濾出 active 的活動，並按 ID 排序
            const activeSales = sales
                .filter(sale => sale.status === 'active')
                .sort((a, b) => a.id - b.id);

            if (activeSales.length === 0) {
                leaderboardSelect.innerHTML = '<option value="">目前沒有進行中的活動</option>';
                return;
            }

            // 加入所有 active 活動
            activeSales.forEach(sale => {
                const option = document.createElement('option');
                option.value = sale.id;
                option.textContent = `活動 ${sale.id} - ${sale.product_name}`;
                leaderboardSelect.appendChild(option);
            });

            // 自動選擇 ID 最小的活動（已排序，取第一個）
            if (activeSales.length > 0) {
                leaderboardSelect.value = activeSales[0].id;
                // 連接 WebSocket
                connectWebSocket();
            }
        }
    } catch (error) {
        console.error('載入排行榜活動列表失敗:', error);
        leaderboardSelect.innerHTML = '<option value="">載入失敗</option>';
    }
}

function changeLeaderboardSale() {
    // 斷開舊的 WebSocket 連接
    disconnectWebSocket();

    // 連接新的 WebSocket
    const saleId = document.getElementById('leaderboardSaleId').value;
    if (saleId) {
        connectWebSocket();
    }
}

// ===== 頁面載入時 =====

window.onload = () => {
    console.log('⚡ 即時競標搶購系統已載入');

    // 載入出價區的活動下拉選單
    loadSalesDropdown();

    // 載入排行榜的活動下拉選單（會自動連接 WebSocket）
    loadLeaderboardSalesDropdown();
};

// ===== 頁面關閉時 =====

window.onbeforeunload = () => {
    disconnectWebSocket();
};
