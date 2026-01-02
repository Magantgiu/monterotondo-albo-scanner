# Albo Pretorio Monterotondo - Scraper

Scarica automaticamente gli atti dal sito dell'albo pretorio di Monterotondo (Hypersic).

## Requisiti

- Python 3.8+
- Chrome/Chromium installato
- ChromeDriver (scarica da https://chromedriver.chromium.org/)

## Installazione

```bash
# Clone il repo
git clone https://github.com/tuoutente/albo-pretorio-monterotondo.git
cd albo-pretorio-monterotondo

# Crea venv
python -m venv venv
source venv/bin/activate  # Su Windows: venv\Scripts\activate

# Installa dipendenze
pip install -r requirements.txt

# Scarica ChromeDriver (mettilo nella cartella del progetto o in PATH)
# https://chromedriver.chromium.org/
```

## Uso

### Scarica atti da una data specifica
```bash
python main.py 20/12/2025
```

### Continua da dove hai lasciato (usa metadata.json)
```bash
python main.py
```

### Ripeti il download da zero
```bash
rm metadata.json
python main.py 01/01/2025
```

## Output

- **PDF**: salvati in `pdfs/YYYY/MM/`
- **Metadati**: salvati in `metadata.json`

Esempio:
```
pdfs/
├── 2025/
│   └── 12/
│       ├── 2960.pdf
│       ├── 2959.pdf
│       ├── 2959_2.pdf
│       └── ...
metadata.json
```

## Features

✅ Scarica **tutti gli allegati** da ogni atto  
✅ **Esclude automaticamente** file `.p7m` e atti con "F.to"  
✅ Supporta **più allegati per atto** (numerati: `2960_2.pdf`, `2960_3.pdf`, etc)  
✅ **Traccia il progresso** con `metadata.json`  
✅ Naviga **tutte le pagine** automaticamente  
✅ **100% locale** - niente cloud, niente dipendenze esterne

## Struttura

```
├── scraper_stateless.py              # Script principale (entry point)
├── core_scraper.py      # Logica di scraping
├── requirements.txt     # Dipendenze Python
├── .gitignore          # File da ignorare in git
└── README.md           # Questo file
```

## Note

- Il primo run potrebbe impiegare **alcuni minuti** (naviga tutte le pagine)
- I successivi run scaricheranno solo gli **atti nuovi** (tracciati in `metadata.json`)
- Se vuoi **ricominciare da zero**, cancella `metadata.json`

## Troubleshooting

**"ChromeDriver non trovato"**
- Scarica da https://chromedriver.chromium.org/
- Mettilo nella cartella del progetto o aggiungi a PATH

**"Nessun atto trovato"**
- Controlla che la data sia corretta (formato: `GG/MM/AAAA`)
- Verifica la connessione Internet
- Prova con una data più indietro: `python main.py 01/12/2025`

## License

MIT
