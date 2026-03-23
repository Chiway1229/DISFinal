# GCP 部署指南 - 即時競標搶購系統

本指南將協助你將即時競標搶購系統部署到 Google Cloud Platform (GCP) 的 Google Kubernetes Engine (GKE)。

## 目錄

- [前置需求](#前置需求)
- [步驟 1: 設定 GCP 專案](#步驟-1-設定-gcp-專案)
- [步驟 2: 建立 GKE 集群](#步驟-2-建立-gke-集群)
- [步驟 3: 建置並推送 Docker 映像](#步驟-3-建置並推送-docker-映像)
- [步驟 4: 部署應用到 GKE](#步驟-4-部署應用到-gke)
- [步驟 5: 設定自動擴展](#步驟-5-設定自動擴展)
- [步驟 6: 驗證部署](#步驟-6-驗證部署)
- [步驟 7: 執行壓測](#步驟-7-執行壓測)
- [監控與維護](#監控與維護)
- [問題排查](#問題排查)

---

## 前置需求

### 本地環境

1. **安裝 Google Cloud SDK**
   ```bash
   # macOS (使用 Homebrew)
   brew install google-cloud-sdk

   # Linux
   curl https://sdk.cloud.google.com | bash
   exec -l $SHELL

   # 安裝 kubectl 組件
   gcloud components install kubectl
   ```

2. **安裝 Docker**
   ```bash
   # macOS
   brew install docker

   # Linux (Ubuntu)
   sudo apt-get update
   sudo apt-get install docker.io
   ```

3. **驗證工具安裝**
   ```bash
   gcloud version
   kubectl version --client
   docker --version
   ```

### GCP 帳號

- 有效的 GCP 帳號 (可使用免費額度)
- 已啟用計費帳號
- 專案管理員權限

---

## 步驟 1: 設定 GCP 專案

### 1.1 登入 GCP

```bash
gcloud auth login
```

### 1.2 建立或選擇專案

```bash
# 建立新專案
export PROJECT_ID="flash-sale-system-$(date +%s)"
gcloud projects create $PROJECT_ID --name="Flash Sale System"

# 或選擇現有專案
export PROJECT_ID="your-existing-project-id"

# 設定為預設專案
gcloud config set project $PROJECT_ID
```

### 1.3 啟用必要的 API

```bash
gcloud services enable \
  container.googleapis.com \
  containerregistry.googleapis.com \
  cloudbuild.googleapis.com \
  compute.googleapis.com
```

### 1.4 設定計費帳號

```bash
# 列出可用的計費帳號
gcloud billing accounts list

# 連結計費帳號到專案
gcloud billing projects link $PROJECT_ID \
  --billing-account=BILLING_ACCOUNT_ID
```

---

## 步驟 2: 建立 GKE 集群

### 2.1 設定區域變數

```bash
# 選擇最近的區域 (台灣選 asia-east1)
export ZONE="asia-east1-a"
export REGION="asia-east1"
gcloud config set compute/zone $ZONE
```

### 2.2 建立 GKE 集群

```bash
gcloud container clusters create flash-sale-cluster \
  --zone=$ZONE \
  --num-nodes=3 \
  --machine-type=e2-standard-2 \
  --enable-autoscaling \
  --min-nodes=3 \
  --max-nodes=20 \
  --enable-autorepair \
  --enable-autoupgrade \
  --disk-size=20GB \
  --disk-type=pd-standard \
  --enable-stackdriver-kubernetes
```

**參數說明:**
- `--num-nodes=3`: 初始節點數量
- `--machine-type=e2-standard-2`: 每個節點 2 vCPU, 8GB RAM
- `--max-nodes=20`: 最大可擴展到 20 個節點
- `--enable-autoscaling`: 啟用節點自動擴展
- `--enable-stackdriver-kubernetes`: 啟用監控

**預估成本:** 每月約 $100-150 USD (3 個節點)

### 2.3 取得集群憑證

```bash
gcloud container clusters get-credentials flash-sale-cluster --zone=$ZONE
```

### 2.4 驗證連線

```bash
kubectl cluster-info
kubectl get nodes
```

你應該會看到 3 個節點處於 `Ready` 狀態。

---

## 步驟 3: 建置並推送 Docker 映像

### 3.1 設定 Docker 認證

```bash
gcloud auth configure-docker
```

### 3.2 建置 Docker 映像

```bash
# 確保在專案根目錄
cd /home/joung/r14725069/DISfinal

# 建置映像
docker build -t gcr.io/$PROJECT_ID/flash-sale-api:v1.0 .
```

### 3.3 測試映像 (選用)

```bash
docker run -p 8000:8000 \
  -e DATABASE_HOST=localhost \
  -e DATABASE_USER=admin \
  -e DATABASE_PASSWORD=password123 \
  -e REDIS_HOST=localhost \
  gcr.io/$PROJECT_ID/flash-sale-api:v1.0
```

### 3.4 推送映像到 Google Container Registry

```bash
docker push gcr.io/$PROJECT_ID/flash-sale-api:v1.0

# 同時標記為 latest
docker tag gcr.io/$PROJECT_ID/flash-sale-api:v1.0 gcr.io/$PROJECT_ID/flash-sale-api:latest
docker push gcr.io/$PROJECT_ID/flash-sale-api:latest
```

---

## 步驟 4: 部署應用到 GKE

### 4.1 更新 Kubernetes 配置檔

在所有 K8s YAML 檔案中，將 `PROJECT_ID` 替換為你的專案 ID：

```bash
# 自動替換所有配置檔中的 PROJECT_ID
cd k8s
sed -i "s/PROJECT_ID/$PROJECT_ID/g" *.yaml
```

### 4.2 建立命名空間

```bash
kubectl apply -f namespace.yaml
```

### 4.3 部署配置和密鑰

**重要:** 在生產環境中修改 `secrets.yaml` 中的密碼！

```bash
# 建議先編輯 secrets.yaml，修改密碼
vim secrets.yaml

# 部署
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml
```

### 4.4 部署 PostgreSQL

```bash
kubectl apply -f postgres-deployment.yaml

# 等待 PostgreSQL 就緒
kubectl wait --for=condition=ready pod -l app=postgres -n flash-sale --timeout=300s
```

### 4.5 部署 Redis

```bash
kubectl apply -f redis-deployment.yaml

# 等待 Redis 就緒
kubectl wait --for=condition=ready pod -l app=redis -n flash-sale --timeout=300s
```

### 4.6 部署應用程式

```bash
kubectl apply -f app-deployment.yaml

# 監控部署狀態
kubectl rollout status deployment/flash-sale-api -n flash-sale
```

### 4.7 部署 HPA (水平自動擴展)

```bash
kubectl apply -f hpa.yaml
```

---

## 步驟 5: 設定自動擴展

### 5.1 驗證 HPA 設定

```bash
kubectl get hpa -n flash-sale

# 查看詳細資訊
kubectl describe hpa flash-sale-api-hpa -n flash-sale
```

### 5.2 驗證 Cluster Autoscaler

```bash
# Cluster autoscaler 已在建立集群時啟用
# 當 Pod 無法調度時會自動增加節點

# 查看節點數量
kubectl get nodes
```

---

## 步驟 6: 驗證部署

### 6.1 檢查所有 Pod 狀態

```bash
kubectl get pods -n flash-sale -w
```

所有 Pod 應該處於 `Running` 狀態。

### 6.2 取得外部 IP

```bash
kubectl get service flash-sale-api-service -n flash-sale

# 等待 EXTERNAL-IP 出現 (可能需要 1-2 分鐘)
```

### 6.3 測試 API

```bash
export API_IP=$(kubectl get service flash-sale-api-service -n flash-sale -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# 測試健康檢查
curl http://$API_IP/health

# 訪問 API 文檔
echo "API Docs: http://$API_IP/docs"
```

### 6.4 查看日誌

```bash
# 查看 API 日誌
kubectl logs -f deployment/flash-sale-api -n flash-sale

# 查看所有 Pod 日誌
kubectl logs -l app=flash-sale-api -n flash-sale --tail=100
```

---

## 步驟 7: 執行壓測

### 7.1 準備壓測環境

在本地或 GCE 實例上執行壓測：

```bash
# 在 GCP 上建立一個壓測實例
gcloud compute instances create load-test-vm \
  --zone=$ZONE \
  --machine-type=n1-standard-4 \
  --image-family=ubuntu-2004-lts \
  --image-project=ubuntu-os-cloud

# SSH 到實例
gcloud compute ssh load-test-vm --zone=$ZONE
```

### 7.2 在壓測實例上安裝依賴

```bash
# 安裝 Python 和工具
sudo apt-get update
sudo apt-get install -y python3-pip git

# 安裝 Locust
pip3 install locust
```

### 7.3 下載壓測腳本

```bash
# 複製你的壓測腳本到實例
# 或直接創建一個簡化版本
cat > load_test.py << 'EOF'
from locust import HttpUser, task, between
import random

class FlashSaleUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        # 註冊和登入
        user_id = random.randint(1000, 9999)
        self.client.post("/auth/register", json={
            "email": f"user{user_id}@test.com",
            "password": "test123",
            "username": f"user{user_id}"
        })

        response = self.client.post("/auth/login", data={
            "username": f"user{user_id}@test.com",
            "password": "test123"
        })
        self.token = response.json()["access_token"]

    @task(10)
    def submit_bid(self):
        self.client.post(
            "/bids",
            json={
                "sale_id": 1,
                "amount": random.randint(1000, 5000)
            },
            headers={"Authorization": f"Bearer {self.token}"}
        )

    @task(3)
    def get_leaderboard(self):
        self.client.get("/bids/1/leaderboard")
EOF
```

### 7.4 執行壓測

```bash
export API_IP="YOUR_API_EXTERNAL_IP"

# 執行 1000 並發用戶的壓測
locust -f load_test.py \
  --host=http://$API_IP \
  --users=1000 \
  --spawn-rate=50 \
  --run-time=5m \
  --headless \
  --csv=results
```

### 7.5 監控自動擴展

在壓測期間，在另一個終端監控擴展情況：

```bash
# 監控 Pod 擴展
watch -n 2 'kubectl get pods -n flash-sale'

# 監控 HPA 狀態
watch -n 2 'kubectl get hpa -n flash-sale'

# 監控節點擴展
watch -n 5 'kubectl get nodes'

# 監控 CPU 使用率
kubectl top pods -n flash-sale
kubectl top nodes
```

### 7.6 預期結果

- **初始狀態:** 3 個 API Pod, 3 個節點
- **壓測開始:** CPU 使用率上升到 70%+
- **第一波擴展 (15-30秒):** Pod 數量增加到 6-12 個
- **第二波擴展 (1-2分鐘):** 節點數量增加到 4-6 個
- **持續擴展:** 根據負載持續擴展,最多 20 個 Pod

---

## 監控與維護

### 使用 GCP Console 監控

1. 前往 [GCP Console - GKE](https://console.cloud.google.com/kubernetes)
2. 選擇你的集群 `flash-sale-cluster`
3. 查看:
   - **工作負載**: Pod 狀態和日誌
   - **服務與 Ingress**: LoadBalancer IP
   - **監控**: CPU、記憶體、網路流量

### 使用 kubectl 監控

```bash
# 查看所有資源
kubectl get all -n flash-sale

# 查看事件
kubectl get events -n flash-sale --sort-by='.lastTimestamp'

# 查看資源使用
kubectl top pods -n flash-sale
kubectl top nodes

# 查看 HPA 狀態
kubectl describe hpa flash-sale-api-hpa -n flash-sale
```

### 查看應用日誌

```bash
# 實時日誌
kubectl logs -f deployment/flash-sale-api -n flash-sale

# 查看最近 100 行
kubectl logs deployment/flash-sale-api -n flash-sale --tail=100

# 查看所有 Pod 日誌
kubectl logs -l app=flash-sale-api -n flash-sale --all-containers=true
```

---

## 問題排查

### Pod 無法啟動

```bash
# 查看 Pod 詳情
kubectl describe pod POD_NAME -n flash-sale

# 查看 Pod 日誌
kubectl logs POD_NAME -n flash-sale

# 常見問題:
# 1. 映像拉取失敗 -> 檢查 GCR 權限
# 2. 連接 DB 失敗 -> 檢查 ConfigMap 和 Secrets
# 3. Init container 失敗 -> 檢查資料庫初始化腳本
```

### 無法取得外部 IP

```bash
# 檢查服務
kubectl get svc flash-sale-api-service -n flash-sale

# 如果一直是 <pending>,檢查防火牆規則
gcloud compute firewall-rules list

# 建立防火牆規則
gcloud compute firewall-rules create allow-flash-sale \
  --allow tcp:80,tcp:8000 \
  --source-ranges 0.0.0.0/0
```

### HPA 無法取得 metrics

```bash
# 檢查 metrics-server
kubectl get deployment metrics-server -n kube-system

# 如果沒有,安裝 metrics-server
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### 資料庫連線錯誤

```bash
# 進入 Pod 測試連線
kubectl exec -it POD_NAME -n flash-sale -- /bin/sh

# 測試 PostgreSQL 連線
nc -zv postgres-service 5432

# 測試 Redis 連線
nc -zv redis-service 6379
```

### 清理資源

```bash
# 刪除所有部署
kubectl delete namespace flash-sale

# 刪除集群 (會刪除所有資源)
gcloud container clusters delete flash-sale-cluster --zone=$ZONE

# 刪除映像
gcloud container images delete gcr.io/$PROJECT_ID/flash-sale-api --quiet

# 刪除專案 (會刪除所有資源並停止計費)
gcloud projects delete $PROJECT_ID
```

---

## 成本估算

### GKE 集群 (3-20 節點)

- **基礎 (3 個 e2-standard-2 節點)**
  - VM: 3 × $49/月 = $147/月
  - 儲存 (60GB PD-Standard): $2.4/月
  - 網路流量: $5-20/月
  - **總計: ~$155-170/月**

- **高峰期 (10 個節點)**
  - VM: 10 × $49/月 = $490/月
  - 其他費用: ~$10/月
  - **總計: ~$500/月**

### 優化建議

1. **使用 Preemptible VMs** (節省 60-80%,但會被中斷)
   ```bash
   gcloud container node-pools create preemptible-pool \
     --cluster=flash-sale-cluster \
     --preemptible \
     --num-nodes=3
   ```

2. **設定自動關機** (非營業時間)
   ```bash
   # 使用 Cloud Scheduler 定時縮減到 0 個節點
   ```

3. **使用 Cloud SQL** 替代自建 PostgreSQL
   - 更穩定,但成本較高 (~$25/月起)

---

## 設定 CI/CD (Cloud Build)

### 啟用自動部署

```bash
# 連結 GitHub repository (在 GCP Console)
gcloud builds submit --config cloudbuild.yaml

# 設定觸發器
gcloud builds triggers create github \
  --repo-name=YOUR_REPO \
  --repo-owner=YOUR_GITHUB_USERNAME \
  --branch-pattern="^main$" \
  --build-config=cloudbuild.yaml
```

每次 push 到 `main` 分支時會自動:
1. 建置 Docker 映像
2. 推送到 GCR
3. 更新 GKE deployment

---

## 下一步

1. **設定域名**: 使用 Cloud DNS 設定自訂域名
2. **啟用 HTTPS**: 使用 Let's Encrypt 或 GCP 管理的憑證
3. **設定備份**: 定期備份 PostgreSQL 資料
4. **監控告警**: 設定 Cloud Monitoring 告警
5. **日誌分析**: 使用 Cloud Logging 進行日誌分析

---

## 參考資源

- [GKE 官方文檔](https://cloud.google.com/kubernetes-engine/docs)
- [Kubernetes 官方文檔](https://kubernetes.io/docs/)
- [GCP 計價器](https://cloud.google.com/products/calculator)
- [Cloud Build 文檔](https://cloud.google.com/build/docs)

---

## 聯繫支援

如有問題,可以:
- 查看 GCP 狀態頁面: https://status.cloud.google.com/
- GCP 支援中心: https://cloud.google.com/support
- Kubernetes Slack: https://kubernetes.slack.com/

---

**祝部署順利! 🚀**
