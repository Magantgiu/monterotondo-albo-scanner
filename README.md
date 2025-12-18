# 📰 Monterotondo Albo Scanner

Sistema automatizzato per scaricare atti dal **Albo Pretorio di Monterotondo**, estrarre il testo, generare bozze per Facebook via **Gemini AI**, e salvare tutto in un **Google Sheet**.

---

## 🎯 Cosa fa

1. **Scarica automaticamente** i PDF dagli atti del Comune
2. **Li salva** nel repository GitHub (`/pdfs/YYYY/MM/`)
3. **Apps Script legge** i PDF da GitHub
4. **Genera bozze civico-satiriche** usando Gemini AI
5. **Salva le bozze** in un Google Sheet per approvazione
6. **Tutto automatico** con trigger schedulati

---

## 🏗️ Architettura

```
┌─────────────────────────────────────────┐
│  GitHub Actions (Workflow)              │
│  ├─ 18:00 UTC                   │
│  ├─ Scarica PDF da Albo Pretorio        │
│  └─ Salva in /pdfs/YYYY/MM/             │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Esempio di GitHub Repository                      │
│  └─ pdfs/2025/11/*.pdf                  │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Google Apps Script (Trigger ogni 24h)   │
│  ├─ Legge PDF da GitHub API             │
│  ├─ Estrae testo (OCR)                  │
│  ├─ Chiama Kimi K2 AI                    │
│  └─ Genera bozze                        │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Google Sheet ("PostGenerati")          │
│  └─ Bozze pronte per approvazione su Wordpress │
└─────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisiti

- ✅ Account GitHub
- ✅ Account Google (Gmail/Sheets/Cloud)
- ✅ Accesso al progetto GCP `albomonterotondo`
- ✅ API Key Gemini

### Setup

#### 1. Clona il repository

```bash
git clone https://github.com/Magantgiu/monterotondo-albo-scanner.git
cd monterotondo-albo-scanner
```

#### 2. Configura GitHub Secrets

Nel tuo repo GitHub, vai a **Settings → Secrets and variables → Actions**

Aggiungi questi secret:

```
SUPABASE_URL          = https://your-project.supabase.co
SUPABASE_KEY          = your-anon-key
ALBO_URL              = https://servizionline.hspromilaprod.hypersicapp.net/...
GCS_KEY_JSON          = {intero JSON del service account}
```

#### 3. Configura Google Apps Script

1. Copia il file `apps_script_github.gs` nel tuo Apps Script
2. Sostituisci `GEMINI_API_KEY = 'AIzaxxxxxx'` con la tua key
3. Aggiungi il **Drive API Service** (Services → Add → Drive API)

#### 4. Crea Google Sheet

Crea un foglio con il tab **"PostGenerati"** e intestazioni:

```
| Data | Filename | FileID | Tipo | Post |
```

#### 5. Aggiungi il Trigger Apps Script

Nel tuo Apps Script:
- **Triggers** → **Add trigger**
- Funzione: `generaPostDaDelibere`
- Evento: `Time-driven` → `Every 6 hours`
- Ora: `07:00` e `19:00`

---

## 📁 Struttura file

```
monterotondo-albo-scanner/
├── core_scraper.py           # Selenium crawler (scarica PDF)
├── scraper_stateless.py      # Upload a GitHub
├── apps_script_github.gs     # Google Apps Script (genera bozze)
├── requirements.txt          # Python dependencies
├── .github/
│   └── workflows/
│       └── scraper.yml       # GitHub Actions workflow
├── pdfs/                     # PDF scaricati (GITIGNORE)
│   └── 2025/11/*.pdf
└── README.md
```

---

## ⚙️ Configurazione

### GitHub Actions Workflow

Il file `.github/workflows/scraper.yml` esegue:

```yaml
schedule:
  - cron: "0 6,18 * * *"   # 06:00 e 18:00 UTC
```

Per cambiare orario, modifica il `cron`:
- `0 6 * * *` = ogni giorno alle 6:00 UTC
- `0 */6 * * *` = ogni 6 ore

### Cartelle PDF

I PDF sono organizzati per data:
```
pdfs/
└── 2025/
    ├── 11/
    │   ├── 2438.pdf
    │   ├── 2439.pdf
    │   └── ...
    └── 12/
        └── ...
```

---

## 🤖 Gemini API

### Ottenere la API Key

1. Vai a: https://aistudio.google.com/app/apikey
2. Clicca **"Create API Key"**
3. Copia la key: `AIzaSy...`

### Limiti Free Tier

- ✅ **60 richieste/minuto**
- ✅ **1,500 richieste/giorno**
- ✅ **Totalmente gratuito**

Per il tuo caso (~50 atti/mese) rientra completamente nel free tier.

---

## 📊 Google Sheet

### Struttura foglio "PostGenerati"

| Data | Filename | FileID | Tipo | Post |
|------|----------|--------|------|------|
| 2025-11-12 | 2438.pdf | 2438 | Civico + Satirico | Monterotondo in Aula... |
| 2025-11-12 | 2439.pdf | 2439 | Civico + Satirico | Monterotondo in Aula... |

### Workflow di approvazione

1. **App Script genera** bozza
2. **Appare nel Sheet** con status "✅ Nuovo"
3. **Tu leggi** e approvi
4. **Pubblichi manualmente** su Facebook
5. **Incolla link** del post nel Sheet

---

## 🔧 Troubleshooting

### GitHub Actions non scarica i PDF

- Verifica che i secret siano impostati correttamente
- Controlla i log dello workflow: **Actions** tab nel repo

### Apps Script non trova i file

```javascript
// Test la connessione
testGithubConnection();
```

Vedi il log per capire se GitHub API funziona.

### Gemini API rate limit

Se raggiungi il limite (60 req/min), attendere 1 minuto.

Lo script ha già `Utilities.sleep(1000)` tra i file per evitarlo.

## 🚨 Limiti e Note

- ⚠️ **PDF OCR**: Funziona bene con delibere testuali, meno bene con scan immagine
- ⚠️ **Gemini**: A volte genera testo incompleto se il prompt è troppo lungo
- ⚠️ **Rate Limit**: GitHub API ha limiti (60 req/ora per IP anonimo)
- ⚠️ **File size**: Limite GitHub 100MB per file

---

## 📈 Statistiche

- 📊 **Atti scaricati**: ~50/mese
- ⏱️ **Tempo di elaborazione**: ~1-2 secondi per atto
- 💰 **Costo totale**: $0 (tutto free tier!)
- 🔄 **Aggiornamenti**: 2 volte al giorno (06:00 e 18:00 UTC)

---

## 🤝 Contributi

Se vuoi migliorare il progetto:

1. Fai un fork
2. Crea un branch: `git checkout -b feature/miglioramento`
3. Commit: `git commit -m "Aggiunto miglioramento"`
4. Push: `git push origin feature/miglioramento`
5. Apri una Pull Request

---

## 📄 Licenza

Progetto open source. Usa come preferisci.

---

## 📞 Contatti

- **Autore**: MonterotondoinAula
- **Repo**: https://github.com/Magantgiu/monterotondo-albo-scanner

---

## 🙏 Ringraziamenti

- Gemini AI per la generazione contenuti
- Google Apps Script per l'automazione
- GitHub Actions per il workflow
- Selenium per lo scraping

---

**Monterotondo in Aula** - Seguiamo la politica locale con ironia e trasparenza! 📰✨
