#!/usr/bin/env python3
"""
scraper_stateless.py - Versione LOCALE (100% file system, no cloud)
- Legge ultima data da file JSON
- Scarica atti via core_scraper.scarica_da()
- Salva PDF in /pdfs/YYYY/MM/
- Salva metadati in metadata.json
"""
import os
import datetime as dt
import json
import sys

# ---------- CONFIG ----------
PDF_FOLDER = "./pdfs"
METADATA_FILE = "./metadata.json"
# -------------------------

def load_metadata() -> dict:
    """Legge metadati da JSON locale"""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠ Errore leggendo metadata: {e}")
            return {}
    return {}

def save_metadata(metadata: dict):
    """Salva metadati in JSON locale"""
    try:
        os.makedirs(os.path.dirname(METADATA_FILE) or ".", exist_ok=True)
        with open(METADATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"⚠ Errore salvando metadata: {e}")

def last_check_date() -> dt.date:
    """Ritorna ultima data salvata o 1 nov 2025 se vuoto"""
    metadata = load_metadata()
    
    if "last_date" in metadata and metadata["last_date"]:
        try:
            return dt.datetime.fromisoformat(metadata["last_date"]).date()
        except:
            pass
    
    # Default: scarica da 3 mesi fa
    default_date = dt.date.today() - dt.timedelta(days=90)
    print(f"⚠ Nessun atto trovato, scarico da {default_date}")
    return default_date

def save_pdf_locally(pdf_bytes: bytes, numero_atto: str, data_pubb: dt.date, allegato_num: int = 1) -> str:
    """Salva PDF nella cartella locale (con numerazione per più allegati)"""
    try:
        os.makedirs(PDF_FOLDER, exist_ok=True)
        
        # Sottocartella per data (YYYY/MM)
        date_folder = os.path.join(PDF_FOLDER, f"{data_pubb:%Y/%m}")
        os.makedirs(date_folder, exist_ok=True)
        
        # Se ci sono più allegati, aggiungi numero
        if allegato_num > 1:
            filename = f"{numero_atto}_{allegato_num}.pdf"
        else:
            filename = f"{numero_atto}.pdf"
        
        filepath = os.path.join(date_folder, filename)
        
        # Se file esiste già, trova un numero libero
        base_path = filepath[:-4]  # Rimuovi .pdf
        counter = allegato_num
        while os.path.exists(filepath):
            counter += 1
            filepath = f"{base_path}_{counter}.pdf"
        
        with open(filepath, 'wb') as f:
            f.write(pdf_bytes)
        
        return filepath
    
    except Exception as e:
        print(f"  ❌ Errore salvando PDF: {e}")
        raise

def add_atto_to_metadata(atto_id: str, data_pubb: dt.date, 
                         oggetto: str, pdf_path: str):
    """Aggiunge atto ai metadati e salva"""
    try:
        metadata = load_metadata()
        
        if "atti" not in metadata:
            metadata["atti"] = []
        
        # Controlla se atto esiste già
        if any(a["id"] == atto_id for a in metadata["atti"]):
            return
        
        # Aggiungi atto
        metadata["atti"].append({
            "id": atto_id,
            "data_pubb": data_pubb.isoformat(),
            "oggetto": oggetto,
            "pdf_path": pdf_path,
            "scaricato_il": dt.datetime.now().isoformat(),
            "status": "nuovo"
        })
        
        # Aggiorna ultima data
        metadata["last_date"] = data_pubb.isoformat()
        
        save_metadata(metadata)
        
    except Exception as e:
        print(f"  ⚠ Errore metadata: {e}")

# ---------- MAIN ----------
if __name__ == "__main__":
    print("🚀 Inizio scaricamento atti (VERSIONE LOCALE)\n")
    
    try:
        # Controlla se è passata una data da linea di comando
        if len(sys.argv) > 1:
            try:
                since = dt.datetime.strptime(sys.argv[1], "%d/%m/%Y").date()
                print(f"📅 Data da linea di comando: {since}\n")
            except ValueError:
                print(f"❌ Formato data non valido: {sys.argv[1]}")
                print(f"   Usa: python scraper_stateless.py 01/01/2025\n")
                since = last_check_date()
        else:
            since = last_check_date()
        
        # Importa scraper
        try:
            from core_scraper import scarica_da
        except ImportError:
            print("❌ Errore: core_scraper.py non trovato!")
            print("   Assicurati che core_scraper.py sia nella stessa cartella")
            sys.exit(1)
        
        count = 0
        errors = 0
        
        print(f"{'='*70}")
        print(f"Inizializzazione dello scraper...")
        print(f"{'='*70}\n")
        
        for atto_id, data_pubb, oggetto, pdf_bytes, allegato_num in scarica_da(since):
            try:
                count += 1
                print(f"\n[{count}] Atto {atto_id} ({data_pubb}) - Allegato #{allegato_num}")
                print(f"    📝 {oggetto[:70]}")
                print(f"    📦 {len(pdf_bytes)} bytes")
                
                # Salva PDF con numero allegato
                pdf_path = save_pdf_locally(pdf_bytes, atto_id, data_pubb, allegato_num)
                print(f"    💾 {pdf_path}")
                
                # Salva metadati
                add_atto_to_metadata(atto_id, data_pubb, oggetto, pdf_path)
                print(f"    ✅ Completato")
            
            except Exception as e:
                errors += 1
                print(f"    ❌ Errore: {e}")
                continue
        
        # Riepilogo
        print(f"\n{'='*70}")
        print(f"🎉 SCARICAMENTO COMPLETATO")
        print(f"{'='*70}")
        print(f"✅ Atti scaricati: {count}")
        print(f"❌ Errori: {errors}")
        print(f"📁 Cartella PDF: {os.path.abspath(PDF_FOLDER)}/")
        print(f"📋 Metadati: {os.path.abspath(METADATA_FILE)}")
        print(f"{'='*70}\n")
    
    except Exception as e:
        print(f"\n❌ ERRORE FATALE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
