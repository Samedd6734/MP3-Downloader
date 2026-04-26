# MP3 Downloader — Müzik Keşfet & İndir

YouTube Music altyapısını kullanarak yüksek kaliteli (192kbps) MP3 indirme arayüzü. Modern, hızlı ve kullanıcı dostu bir deneyim sunar.

## ✨ Özellikler

- **YouTube Music Entegrasyonu:** Gerçek sanatçı ve şarkı meta verileri.
- **Top Result Önceliği:** Aramalarda en alakalı sanatçıyı otomatik profile çıkarma.
- **Resmi Sanatçı Kartları:** Sanatçı abone sayısı ve profil detayları.
- **Sonsuz Kaydırma (Lazy Loading):** Sanatçı sayfalarında tüm şarkılara kesintisiz erişim.
- **Hızlı Dönüştürme:** Arka planda kuyruğa alınan ve anında indirilen MP3 dosyaları.

## 🚀 Kurulum

Projeyi yerel bilgisayarınızda çalıştırmak için aşağıdaki adımları izleyin:

### 1. Gereksinimler
Bilgisayarınızda Python 3.9+ ve FFmpeg kurulu olmalıdır.

### 2. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
```


### 3. Çalıştırın
```bash
uvicorn main:app --reload
```
Uygulamaya `http://localhost:8000` adresinden erişebilirsiniz.

## 🛠️ Teknoloji Yığını

- **Backend:** FastAPI (Python)
- **Frontend:** Vanilla JS, CSS3, HTML5
- **İndirme:** yt-dlp, ytmusicapi
- **Dönüştürme:** FFmpeg

## 📝 Notlar
Bu proje eğitim amaçlı geliştirilmiştir. İndirilen içeriklerin telif hakları ilgili sanatçı ve platformlara aittir.
