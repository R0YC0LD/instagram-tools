# Instagram Araçları — Kurulum, kullanım, derleme

🌐 [English](USAGE.md) · **Türkçe** · [← README'ye dön](../README.tr.md)

İçindekiler: [1. Kurulum (hazır exe)](#1-kurulum-hazır-exe) · [2. Açılış ve giriş](#2-açılış-ve-giriş) · [3. Araçların kullanımı](#3-araçların-kullanımı) · [4. Ayarlar, dosyalar ve kaldırma](#4-ayarlar-dosyalar-ve-kaldırma) · [5. Kaynaktan çalıştırma](#5-kaynaktan-çalıştırma) · [6. Exe'yi kendin derle](#6-exeyi-kendin-derle) · [7. Sorun giderme](#7-sorun-giderme)

---

## 1. Kurulum (hazır exe)

**Kurulum yok**, Python da **gerekmez**.

1. **Tıkla ve indir:** [**InstagramTools.exe**](https://github.com/R0YC0LD/instagram-tools/releases/latest/download/InstagramTools.exe) (yaklaşık 28 MB). Bağlantı hep en yeni sürümü indirir; tüm sürümler [Releases sayfasında](https://github.com/R0YC0LD/instagram-tools/releases).
2. Dosyayı istediğin yere (Masaüstü, Belgeler…) koy ve **çift tıkla**.
3. *İsteğe bağlı:* dosyanın SHA-256 değerini sürüm sayfasındaki `SHA256.txt` ile karşılaştır  
   (PowerShell'de `Get-FileHash .\InstagramTools.exe -Algorithm SHA256`).

**"Windows bilgisayarınızı korudu" (SmartScreen) uyarısı mı çıktı?** Exe dijital olarak imzalı değil (imza ücretlidir), bu yüzden Windows "bilinmeyen yayıncı" uyarısı verebilir. **Ek bilgi → Yine de çalıştır**'a tıkla. İstersen kaynak kodun tamamı bu depoda; exe'yi kendin de derleyebilirsin (bölüm 6).

Yalnızca Windows 10/11 (64 bit) desteklenir. Aynı anda yalnızca **bir kopya** çalışır.

## 2. Açılış ve giriş

Kısa bir açılış ekranından sonra (atlamak için tıkla ya da bir tuşa bas) **Giriş** sayfası gelir. Program Windows'un diliyle açılır; sol alttaki **DİL** kutusuyla istediğin an değiştirebilirsin.

**A · Şifreyle giriş** — kullanıcı adı ve şifreni yaz (şifre yazarken görünür; gizlemek için *Gizle*'yi işaretle). 2 adımlı doğrulaman varsa program 6 haneli kodu (ya da SMS / yedek kodu) sorar.

**B · Tarayıcı oturumuyla giriş** — A yöntemi *"Your version of Instagram is out of date"* derse bunu kullan:

1. Normal tarayıcında **instagram.com**'a giriş yap (2 adımlı kod dahil).
2. `F12` → **Application** (Chrome/Edge) ya da **Storage** (Firefox) sekmesi → **Cookies** → `https://www.instagram.com`.
3. `sessionid` değerini kopyala, **B** kutusuna yapıştır, **Oturumla giriş yap**'a tıkla.

Her seferinde giriş yapmak istemiyorsan **Bu bilgisayarda oturumu şifreli hatırla**'yı işaretle. Oturum Windows DPAPI ile şifrelenir (yalnızca senin Windows hesabın açabilir). Şifren hiç kaydedilmez.

Girişten sonra sol menüdeki tüm sayfalar açılır. **Hız profili** kutusu (sol altta) tüm araçlar için geçerlidir: **Güvenli** en yavaş, **Dengeli** varsayılan, **Hızlı** en hızlı ama daha risklidir.

## 3. Araçların kullanımı

Tüm temizlik araçları aynı şekilde çalışır: **tara → planı kontrol et → onayla → program kendi başına bitirir.** Pencereyi açık bırak (bilgisayar uykuya geçmez). İstediğin an **Durdur**'a basabilirsin.

- Bir satırı korumak için **çift tıkla** (yeşil **Korumalı ★**); tekrar çift tıklarsan kalkar. Korumalı satırlara dokunulmaz, seçimin bir sonraki açılışta da hatırlanır.
- Geri alınamaz işlemlerde **onay kelimesini yazman** istenir (Türkçede `SİL` / `KALDIR`, İngilizcede `DELETE` / `REMOVE`).
- Instagram uyarı verirse program yavaşlar, dinlenir ve kendiliğinden devam eder; ciddi uyarıda durur. Birkaç saat sonra yeniden başlat — yeniden tarayınca kalanlardan devam eder.

### Sohbet seç / Mesajlar (DM araçları)
**Sohbet seç** sayfasında bir sohbeti seç (çift tıkla ya da *Bu sohbeti seç*). **Mesajlar** konuşmayı yükler. Gri satırlar karşı tarafındır, geri çekilemez. Kendi mesajlarını seçip **Seçili mesajlarımı geri çek** (herkes için silinir) ya da **Sohbeti komple sil** (sohbeti gelen kutundan kaldırır) de. *Kelime(ler)* alanına yazarsan yalnızca eşleşen mesajlar listelenir.

### DM temizlik (otomatik)
1. **Korunacak son sohbet sayısı**nı ayarla (varsayılan 20); istersen *Sabitlenmiş sohbetleri koru*.
2. **Sohbetleri tara ve planla**'ya bas. Liste *Korunacak* / *Silinecek* olarak gelir.
3. Ayrıca korumak istediğin sohbetlere çift tıkla.
4. **Otomatik temizliği başlat**'a bas ve `SİL` yaz.

İsteğe bağlı: *Silmeden önce kendi mesajlarımı da geri çek* (çok yavaş; karşı taraftan da kaybolur). Bu seçenek kapalıysa karşı taraf sohbeti kendi tarafında görmeye devam eder.

### Sohbet yedekle
1. **Yedek klasörü**nü seç (varsayılan: `Belgeler\Instagram Araçları\Yedekler`) ve indirilecekleri işaretle: görseller (varsayılan), videolar, sesli mesajlar.
2. **Sohbetleri yükle**, istediklerini seç (Ctrl/Shift ile ya da *Hepsini seç*).
3. **Seçilenleri yedekle.**

Her kişi için bir klasör açılır; içinde `sohbet.txt` ve `gorseller` klasörü olur. Var olan dosyalar atlanır, yani yeniden çalıştırınca yedek yalnızca tamamlanır. Bu araç sadece okur, hiçbir şey silmez.

### Story arşivi
Bir tarih yaz (ya da *1 ay / 6 ay / 1 yıl önce*'ye tıkla), **Arşivi tara ve planla**'ya bas, saklamak istediğin günleri koru, sonra **Eski storyleri sil** ve `SİL` yaz.

### Engeller
**Engelleri tara ve planla** engellediğin herkesi listeler. Engelli kalması gerekenleri koru, sonra **Engelleri kaldır** ve `KALDIR` yaz.

### Beğeniler
**Beğenileri tara ve planla** beğendiğin gönderi ve reelleri listeler (yorum beğenileri dahil değil). Kalsın istediklerini koru, sonra **Beğenileri kaldır**.

### Kaydedilenler
**Kaydedilenleri tara ve planla** kaydettiğin gönderi ve reelleri listeler. **Kayıtları kaldır** onları *Kaydedilenler*'den çıkarır; gönderilerin kendisi silinmez.

### Hesap bilgisi
Ad, kullanıcı ID, **hesabın ne zaman açıldığı**, yaşı, ülke, eski kullanıcı adları, sayılar, hesap türü, biyografi, bağlantı ve gizlenmiş e-posta / telefonu gösterir. Yenilemek için **Yenile**'ye bas. (Instagram açılış tarihini her hesap için vermez.)

## 4. Ayarlar, dosyalar ve kaldırma

| Ne | Nerede |
|---|---|
| Ayarlar, koruma listeleri, kayıtlı oturum, günlük | `%LOCALAPPDATA%\IGDMTool\` (Gezgin adres çubuğuna yapıştır) |
| Günlük dosyası | `%LOCALAPPDATA%\IGDMTool\igdmtool.log` (ya da uygulamadaki *Günlük dosyasını aç* bağlantısı) |
| Sohbet yedekleri | seçtiğin klasör (varsayılan `Belgeler\Instagram Araçları\Yedekler`) |

**Kaldırma:** uygulamada **Çıkış yap ve oturumu sil**'e bas (kayıtlı girişi siler), `InstagramTools.exe` dosyasını sil, istersen `%LOCALAPPDATA%\IGDMTool` klasörünü de sil. Kayıt defterine (registry) hiçbir şey yazılmaz.

## 5. Kaynaktan çalıştırma

Windows, [Python 3.12](https://www.python.org/downloads/) (*Add python.exe to PATH* işaretli) ve Git gerekir.

```powershell
git clone https://github.com/R0YC0LD/instagram-tools.git
cd instagram-tools
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python src\igdm_launcher.py
```

## 6. Exe'yi kendin derle

```powershell
git clone https://github.com/R0YC0LD/instagram-tools.git
cd instagram-tools
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Betik `.venv` oluşturur, bağımlılıkları kurar, ikonu yeniden çizer, **231 testi çalıştırır** ve PyInstaller ile tek dosyalık, konsolsuz bir exe üretir. Sonuç: `dist\InstagramTools.exe` ve `dist\SHA256.txt` (yaklaşık 28 MB; ilk derleme birkaç dakika sürer). Testleri atlamak için `-SkipTests` ekle.

Yalnızca testler: `.\.venv\Scripts\python tests\run_all.py` (sahte istemci kullanır, Instagram'a hiç bağlanmaz).

## 7. Sorun giderme

| Sorun | Ne yapmalı |
|---|---|
| Şifreyle girişte *"Your version of Instagram is out of date"* | **B · Tarayıcı oturumuyla giriş** yöntemini kullan (bölüm 2). |
| *"Instagram ek doğrulama istiyor"* | Instagram uygulamasında *"Bu bendim"* bildirimini onayla, tekrar dene. |
| Oturum süresi doldu | **Çıkış yap ve oturumu sil**, sonra yeniden giriş yap. |
| Instagram uyarısı / sınırlama | Program kendiliğinden dinlenir. Durduysa birkaç saat bekleyip yeniden tara. Uzun listelerde **Güvenli** hızı kullan. |
| "Program zaten açık" | Aynı anda tek kopya çalışır. Diğerini kapat (Görev Yöneticisi'ne bak). |
| Antivirüs exe'yi işaretledi | İmzasız PyInstaller exe'leri bazen yanlışlıkla işaretlenir. SHA-256'yı karşılaştır ya da kendin derle (bölüm 6). |
| Başka bir şey | Günlüğü aç (`%LOCALAPPDATA%\IGDMTool\igdmtool.log`) ve bir [issue](https://github.com/R0YC0LD/instagram-tools/issues) aç — **kullanıcı adlarını sil ve `sessionid` değerini asla paylaşma**. |
