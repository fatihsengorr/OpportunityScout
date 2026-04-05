# OpportunityScout — Deployment Rehberi (REHBER.md)

> Bu rehber, OpportunityScout'u sıfırdan üretime kadar deploy etmek için gereken
> HER adımı, kopyala-yapıştır komutlarıyla anlatır. 3 senaryo var:
>
> **A.** Local Development (hızlı test)
> **B.** AWS EC2 Production (7/24 çalışan sistem)
> **C.** Mevcut n8n altyapısına entegrasyon

---

## Ön Gereksinimler (Tüm Senaryolar İçin Ortak)

### 1. Telegram Bot Oluşturma

Bu adımı önce yap — hem local hem production'da lazım.

```
1. Telegram'da @BotFather'a git
2. /newbot yaz
3. İsim ver: OpportunityScout
4. Username ver: opportunity_scout_fatih_bot (unique olmalı)
5. Sana bir TOKEN verecek — kaydet:
   Örnek: 7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxx

6. Kendi Chat ID'ni öğren:
   - Telegram'da @userinfobot'a git
   - /start yaz
   - Sana chat_id verecek (örnek: 987654321)
```

### 2. Anthropic API Key

```
1. https://console.anthropic.com adresine git
2. Settings → API Keys
3. "Create Key" → İsim: OpportunityScout
4. Key'i kaydet:
   Örnek: sk-ant-api03-xxxxxxxxxxxxxxxxxxxx
```

### 3. API Maliyeti Tahmini

```
Günlük tarama (Tier 1):
  - ~20 web search çağrısı × ~4K token input + ~2K output
  - ~5 batch analysis çağrısı × ~8K token input + ~4K output  
  - Sonnet 4 fiyatıyla: ~$0.40-0.80/gün

Haftalık deep dive (Opus):
  - ~3 deep dive × ~10K input + ~8K output
  - Opus fiyatıyla: ~$1.50-3.00/hafta

Aylık toplam: ~$20-35 (aktif kullanımda)
```

---

## SENARYO A: Local Development (Hızlı Test)

> Amacı: Sistemi kendi bilgisayarında çalıştırıp test etmek.
> Süre: ~15 dakika

### A1. Projeyi Kur

```bash
# Proje klasörünü oluştur (veya tar.gz'den çıkar)
mkdir -p ~/projects
cd ~/projects

# Eğer tar.gz indirdiysen:
tar -xzf opportunity-scout.tar.gz
cd opportunity-scout

# Eğer Git repo'dan klonlayacaksan:
# git clone https://github.com/YOUR_USER/opportunity-scout.git
# cd opportunity-scout
```

### A2. Python Ortamını Hazırla

```bash
# Python 3.11+ gerekli — kontrol et
python3 --version
# Python 3.11.x veya üstü olmalı

# Virtual environment oluştur
python3 -m venv venv

# Aktifleştir
source venv/bin/activate   # Linux/Mac
# veya Windows: venv\Scripts\activate

# Bağımlılıkları kur
pip install -r requirements.txt

# Doğrulama
python -c "import anthropic; import yaml; import feedparser; print('✅ All dependencies OK')"
```

### A3. Environment Variables

```bash
# .env dosyasını oluştur
cp .env.example .env

# Düzenle — nano, vim, veya favori editörün
nano .env
```

**.env dosyası şu şekilde olmalı:**

```bash
# ─── ZORUNLU ──────────────────────────────────────────────
ANTHROPIC_API_KEY=sk-ant-api03-SENIN_KEY_IN_BURAYA
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=987654321

# ─── OPSİYONEL (local test için gerekmez) ────────────────
N8N_USER=admin
N8N_PASSWORD=changeme
N8N_WEBHOOK_SECRET=random-secret-here
PG_USER=scout
PG_PASSWORD=scoutpass
```

```bash
# .env'yi yükle (her terminal oturumunda)
export $(grep -v '^#' .env | xargs)

# veya otomatik yükleme için .bashrc/.zshrc'ye ekle:
# echo 'cd ~/projects/opportunity-scout && export $(grep -v "^#" .env | xargs)' >> ~/.bashrc
```

### A4. Sistemi Başlat

```bash
# Klasörleri oluştur ve veritabanını başlat
python -m src.cli init

# Çıktı:
# 🚀 OpportunityScout Initialized!
#    Database: {'total_opportunities': 0, ...}
#    Directories: data/, logs/, exports/ created
```

### A5. İlk Taramayı Çalıştır

```bash
# Tier 1 tarama — tüm yüksek öncelikli kaynaklar
python -m src.cli scan --tier 1

# Bu 3-10 dakika sürebilir (API çağrıları + rate limiting)
# Telegram'a uyarılar düşecek
```

```bash
# Sonuçları gör
python -m src.cli portfolio --top 10

# İstatistikleri gör
python -m src.cli stats
```

### A6. Diğer Komutları Test Et

```bash
# Bir fikri puanla
python -m src.cli score "AI-powered UK Building Safety Act compliance auditing for social housing providers"

# Günlük özet gönder
python -m src.cli digest

# Bir konuda deep dive
python -m src.cli deep_dive "UK fire door market AI inspection"

# Kaynak performansı
python -m src.cli sources

# Self-improvement döngüsü
python -m src.cli evolve
```

### A7. Telegram Bot'u Interactive Modda Çalıştır

```bash
# Bot'u başlat — Telegram'dan komut gönderebilirsin
python -m src.cli serve

# Telegram'da bot'una git ve şunları dene:
# /start
# /scout
# /portfolio
# /stats
```

**Ctrl+C ile durdur.**

---

## SENARYO B: AWS EC2 Production (7/24 Sistem)

> Amacı: Sistemin sürekli çalışması, otomatik tarama yapması.
> Süre: ~45 dakika
> Maliyet: ~$5-15/ay (t3.small veya t3.micro)

### B1. EC2 Instance Oluştur

```
AWS Console → EC2 → Launch Instance

Ayarlar:
  Name:            opportunity-scout
  AMI:             Ubuntu 24.04 LTS (HVM, SSD)
  Instance type:   t3.small (2 vCPU, 2 GB RAM)
                   veya t3.micro (1 vCPU, 1 GB RAM) — yeterli
  Key pair:        Mevcut key'ini seç veya yeni oluştur
  Security group:  
    - SSH (22) → Senin IP'n
    - HTTP (5678) → Senin IP'n (n8n web UI için)
    - HTTPS (443) → Senin IP'n (Caddy reverse proxy için)
  Storage:         20 GB gp3
  
  Tag: Project = OpportunityScout
```

### B2. SSH ile Bağlan

```bash
# Key dosyasının izinlerini ayarla
chmod 400 ~/your-key.pem

# Bağlan
ssh -i ~/your-key.pem ubuntu@EC2_PUBLIC_IP

# Örnek:
# ssh -i ~/keys/scout-key.pem ubuntu@54.123.45.67
```

### B3. Sunucuyu Hazırla

```bash
# Sistem güncellemesi
sudo apt update && sudo apt upgrade -y

# Gerekli paketler
sudo apt install -y python3 python3-pip python3-venv git docker.io docker-compose-v2 nginx

# Docker'ı başlat ve otomatik başlatmaya ekle
sudo systemctl start docker
sudo systemctl enable docker

# Kullanıcıyı docker grubuna ekle
sudo usermod -aG docker ubuntu
# YENİDEN BAĞLAN (grup değişikliği için):
exit
ssh -i ~/your-key.pem ubuntu@EC2_PUBLIC_IP
```

### B4. Projeyi Yükle

```bash
# Proje klasörü
sudo mkdir -p /opt/opportunity-scout
sudo chown ubuntu:ubuntu /opt/opportunity-scout

# YÖNTEM 1: Git ile (önerilen)
cd /opt
git clone https://github.com/YOUR_USER/opportunity-scout.git

# YÖNTEM 2: SCP ile local'den kopyala (kendi bilgisayarından)
# (Başka bir terminal penceresinde)
# scp -i ~/your-key.pem opportunity-scout.tar.gz ubuntu@EC2_PUBLIC_IP:/opt/
# Sonra EC2'de:
# cd /opt && tar -xzf opportunity-scout.tar.gz

cd /opt/opportunity-scout
```

### B5. Environment Variables

```bash
cp .env.example .env
nano .env
# ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID doldur
# N8N_USER ve N8N_PASSWORD güçlü şifreler koy

# Dosya izinlerini kısıtla (güvenlik)
chmod 600 .env
```

### B6. Docker ile Deploy Et

```bash
cd /opt/opportunity-scout

# İmajları build et ve başlat
docker compose up -d --build

# Durumu kontrol et
docker compose ps

# Çıktı şöyle olmalı:
# NAME                  STATUS
# opportunity-scout     Up (running)
# scout-n8n             Up (running)
# scout-postgres        Up (running)

# Logları izle
docker compose logs -f scout
# Ctrl+C ile çık
```

### B7. n8n Web UI'a Eriş

```bash
# Tarayıcıda:
# http://EC2_PUBLIC_IP:5678

# .env'deki N8N_USER ve N8N_PASSWORD ile giriş yap
```

### B8. n8n Workflow'ları İçe Aktar

```
n8n Web UI'da:

1. Sol menü → Workflows → Import from File
2. n8n/daily_scan.json dosyasını yükle
3. "Daily Trigger (06:00 UTC)" node'una tıkla → Enable et
4. Workflow'u ACTIVATE et (sağ üst toggle)

5. Aynı şekilde n8n/weekly_deep_dive.json'ı da import et
6. Onu da ACTIVATE et

Artık:
  - Her gün 06:00 UTC → Tier 1 tarama + günlük özet
  - Her Pazartesi 03:00 UTC → Tier 2 tarama + evrim + haftalık rapor
```

### B9. Systemd Service (Docker Compose Otomatik Başlatma)

```bash
sudo nano /etc/systemd/system/opportunity-scout.service
```

```ini
[Unit]
Description=OpportunityScout Docker Stack
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/opportunity-scout
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable opportunity-scout
sudo systemctl start opportunity-scout

# Sunucu restart olduğunda otomatik başlayacak
```

### B10. Caddy ile HTTPS (Opsiyonel ama Önerilen)

> n8n'e güvenli erişim için. Bir domain gerektirir (örn: scout.yourdomain.com).

```bash
# Caddy kur
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

```bash
sudo nano /etc/caddy/Caddyfile
```

```
scout.yourdomain.com {
    reverse_proxy localhost:5678
}
```

```bash
sudo systemctl restart caddy

# Artık https://scout.yourdomain.com üzerinden n8n'e erişebilirsin
# DNS'te A kaydı: scout.yourdomain.com → EC2_PUBLIC_IP
```

### B11. Monitoring ve Sağlık Kontrolü

```bash
# Crontab ile basit health check
crontab -e
```

```cron
# Her 6 saatte bir health check — bot çalışıyor mu?
0 */6 * * * cd /opt/opportunity-scout && docker compose ps --format json | python3 -c "import sys,json; data=json.loads(sys.stdin.read()); [print(f'⚠️ {s[\"Name\"]} is {s[\"State\"]}') for s in data if s.get('State') != 'running']" 2>/dev/null || curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" -d "chat_id=${TELEGRAM_CHAT_ID}&text=⚠️ OpportunityScout health check failed!"
```

```bash
# Log rotasyonu (loglar çok büyümesin)
sudo nano /etc/logrotate.d/opportunity-scout
```

```
/opt/opportunity-scout/logs/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

---

## SENARYO C: Mevcut n8n Altyapısına Entegrasyon

> Zaten AWS'de çalışan bir n8n instance'ın varsa (eu-west-2),
> sadece scout'u yanına eklemen yeterli.

### C1. Scout'u Mevcut Sunucuya Kur

```bash
ssh -i your-key.pem ubuntu@YOUR_N8N_SERVER_IP

# Scout'u kur (Docker olmadan, sadece Python)
sudo mkdir -p /opt/opportunity-scout
sudo chown ubuntu:ubuntu /opt/opportunity-scout

# Dosyaları yükle (git clone veya scp)
cd /opt/opportunity-scout

# Python ortamını hazırla
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env ayarla
cp .env.example .env
nano .env

# Başlat ve test et
export $(grep -v '^#' .env | xargs)
python -m src.cli init
python -m src.cli scan --tier 1
```

### C2. Mevcut n8n'e Workflow'ları Ekle

```
1. Mevcut n8n web UI'ına gir
2. Workflows → Import from File
3. daily_scan.json ve weekly_deep_dive.json'ı import et
4. Her iki workflow'daki "Execute Command" node'larında path'i kontrol et:
   - cd /opt/opportunity-scout && /opt/opportunity-scout/venv/bin/python -m src.cli scan --tier 1
   (venv path'ini eklemeyi unutma!)
5. Workflow'ları ACTIVATE et
```

### C3. Telegram Bot'u Systemd Service Olarak Çalıştır

```bash
sudo nano /etc/systemd/system/scout-telegram.service
```

```ini
[Unit]
Description=OpportunityScout Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/opportunity-scout
EnvironmentFile=/opt/opportunity-scout/.env
ExecStart=/opt/opportunity-scout/venv/bin/python -m src.cli serve
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable scout-telegram
sudo systemctl start scout-telegram

# Durumu kontrol et
sudo systemctl status scout-telegram

# Logları gör
journalctl -u scout-telegram -f
```

---

## Güncelleme ve Bakım

### Kodu Güncelle

```bash
# Git ile
cd /opt/opportunity-scout
git pull origin main

# Docker ile (Senaryo B)
docker compose down
docker compose up -d --build

# Systemd ile (Senaryo C)
sudo systemctl restart scout-telegram
```

### Veritabanını Yedekle

```bash
# Manuel yedek
cp /opt/opportunity-scout/data/opportunity_scout.db \
   /opt/opportunity-scout/data/backup_$(date +%Y%m%d).db

# Otomatik günlük yedek (crontab'a ekle)
0 2 * * * cp /opt/opportunity-scout/data/opportunity_scout.db /opt/opportunity-scout/data/backup_$(date +\%Y\%m\%d).db
# 30 günden eski yedekleri sil
0 3 * * * find /opt/opportunity-scout/data/ -name "backup_*.db" -mtime +30 -delete
```

### Kaynak Ekle veya Düzenle

```bash
nano /opt/opportunity-scout/config/sources.yaml

# Yeni kaynak formatı:
# - name: "Yeni Kaynak Adı"
#   type: web_search     # veya rss, reddit, api
#   query: "arama sorgusu"
#   tier: 1              # 1=günlük, 2=haftalık, 3=aylık
#   tags: [etiket1, etiket2]
#   signal_score: 7
#   scan_frequency: daily
```

### Puanlama Ağırlıklarını Ayarla

```bash
nano /opt/opportunity-scout/config/config.yaml

# scoring.weights bölümünde ağırlıkları değiştir
# Örnek: Eğer "time to revenue" daha önemliyse:
#   time_to_revenue: 3.0  (varsayılan 2.5)
```

---

## Sorun Giderme

### "Telegram send failed" Hatası

```bash
# Bot token'ı doğrula
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
# {"ok":true,"result":{"id":...}} dönmeli

# Chat ID'yi doğrula
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${TELEGRAM_CHAT_ID}&text=Test message"
```

### "Anthropic API error" Hatası

```bash
# API key'i test et
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: ${ANTHROPIC_API_KEY}" \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-sonnet-4-20250514","max_tokens":100,"messages":[{"role":"user","content":"Say OK"}]}'
```

### Docker Container Başlamıyor

```bash
# Logları kontrol et
docker compose logs scout
docker compose logs n8n

# Yeniden build et
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Veritabanı Bozuldu

```bash
# Yedekten geri yükle
cp /opt/opportunity-scout/data/backup_YYYYMMDD.db \
   /opt/opportunity-scout/data/opportunity_scout.db

# Veya sıfırdan başlat
rm /opt/opportunity-scout/data/opportunity_scout.db
python -m src.cli init
```

### RSS Feed'ler Çalışmıyor

```bash
# Feed URL'ini test et
curl -s "https://www.constructionenquirer.com/feed/" | head -20
# XML dönmeli. 403/404 alıyorsan feed URL değişmiş — sources.yaml'ı güncelle
```

---

## Hızlı Referans Kartı

```
┌─────────────────────────────────────────────────────────────┐
│  GÜNLÜK KULLANIM                                            │
│                                                              │
│  Telegram'dan:           CLI'dan:                           │
│  /scout     → Tara       python -m src.cli scan --tier 1    │
│  /portfolio → Portföy    python -m src.cli portfolio        │
│  /stats     → İstatistik python -m src.cli stats            │
│                          python -m src.cli score "fikir"    │
│                          python -m src.cli deep_dive "konu" │
│                          python -m src.cli digest           │
│                          python -m src.cli evolve           │
│                                                              │
│  OTOMATİK (n8n ile):                                        │
│  06:00 UTC → Tier 1 tarama + günlük özet                    │
│  Pazartesi 03:00 → Tier 2 + evrim + haftalık rapor          │
│                                                              │
│  UYARI TİPLERİ:                                             │
│  🔥 FIRE (≥150) → Anında Telegram mesajı                   │
│  ⭐ HIGH (≥120) → Anında Telegram mesajı                    │
│  📊 MEDIUM/LOW  → Günlük özette                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Önerilen İlk Hafta Planı

```
GÜN 1 (Bugün):
  ✅ Local'de kur ve test et (Senaryo A)
  ✅ İlk Tier 1 taramayı çalıştır
  ✅ 2-3 fikri /score ile puanla
  ✅ Sonuçları değerlendir — scoring mantıklı mı?

GÜN 2-3:
  ✅ Sources.yaml'a kendi kaynaklarını ekle
  ✅ Founder profile'ı incele, eksik var mı?
  ✅ Birkaç tane daha tarama çalıştır
  ✅ FIRE/HIGH çıkanlar için deep dive yap

GÜN 4-5:
  ✅ AWS EC2'ye deploy et (Senaryo B veya C)
  ✅ n8n workflow'larını aktifleştir
  ✅ Telegram bot'un 7/24 çalıştığını doğrula

GÜN 6-7:
  ✅ İlk haftalık raporu al
  ✅ Evrim döngüsünü çalıştır
  ✅ Düşük performanslı kaynakları düzenle
  ✅ İlk gerçek fırsatı değerlendir
```
