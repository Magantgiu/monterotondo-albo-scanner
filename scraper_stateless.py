#!/usr/bin/env python3
"""
Cloud-ready wrapper:
- legge ultima data da file JSON locale
- scarica solo nuovi atti via core_scraper.scarica_da()
- salva PDF in cartella locale /pdfs
- scrive metadati in JSON locale
"""
import os
import datetime as dt
import json

# ---------- CONFIG ----------
PDF_FOLDER = "./pdfs"
METADATA_FILE = "./metadata.json"
# -------------------------

def load_metadata() -> dict:
    """Carica metadati da file JSON locale"""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠ Errore leggendo metadati: {e}")
            return {}
    return {}

def save_metadata(metadata: dict):
    """Salva metadati in file JSON locale"""
    try:
        with open(METADATA_FILE, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        print(f"  ✅ Metadati salvati in {METADATA_FILE}")
    except Exception as e:
        print(f"  ⚠ Errore salvando metadati: {e}")

def last_check_date() -> dt.date:
    """Ultima data già salvata (o 1 nov 2025 se vuoto)."""
    metadata = load_metadata()
    
    if "last_date" in metadata:
        try:
            return dt.datetime.fromisoformat(metadata["last_date"]).date()
        except:
            pass
    
    print("⚠ Nessun atto trovato, scarico da 1 nov 2025")
    return dt.date(2025, 11, 1)

def save_pdf_locally(pdf_bytes: bytes, numero_atto: str, data_pubb: dt.date) -> str:
    """Salva PDF nella cartella locale"""
    try:
        # Crea cartella se non esiste
        os.makedirs(PDF_FOLDER, exist_ok=True)
        
        # Crea sottocartella per data (YYYY/MM)
        date_folder = os.path.join(PDF_FOLDER, f"{data_pubb:%Y/%m}")
        os.makedirs(date_folder, exist_ok=True)
        
        # Salva il file
        filename = f"{numero_atto}.pdf"
        filepath = os.path.join(date_folder, filename)
        
        with open(filepath, 'wb') as f:
            f.write(pdf_bytes)
        
        print(f"  ✅ PDF salvato: {filepath}")
        return filepath
    
    except Exception as e:
        print(f"  ❌ Errore salvando PDF: {e}")
        raise

def save_atto_metadata(atto_id: str, data_pubb: dt.date, 
                       oggetto: str, pdf_path: str):
    """Salva metadati atto in JSON locale"""
    try:
        metadata = load_metadata()
        
        # Inizializza lista atti se non esiste
        if "atti" not in metadata:
            metadata["atti"] = []
        
        # Aggiungi l'atto
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
        print(f"  ✅ Metadati salvati localmente")
        
    except Exception as e:
        print(f"  ⚠ Errore salvando metadati: {e}")

# ---------- MAIN ----------
if __name__ == "__main__":
    print("🚀 Inizio scaricamento atti...\n")
    
    try:
        since = last_check_date()
        print(f"🔍 Scaricando atti dal {since}\n")
        
        from core_scraper import scarica_da
        
        count = 0
        for atto_id, data_pubb, oggetto, pdf_bytes in scarica_da(since):
            try:
                count += 1
                print(f"\n[{count}] Atto {atto_id} ({data_pubb})")
                print(f"     📝 {oggetto[:70]}")
                print(f"     📦 {len(pdf_bytes)} bytes")
                
                # Salva localmente
                pdf_path = save_pdf_locally(pdf_bytes, atto_id, data_pubb)
                
                # Salva metadati localmente
                save_atto_metadata(atto_id, data_pubb, oggetto, pdf_path)
                
                print(f"     ✅ Completato!")
            
            except Exception as e:
                print(f"     ❌ Errore: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"🎉 Completato! Scaricati {count} atti")
        print(f"📁 PDF: {os.path.abspath(PDF_FOLDER)}/")
        print(f"📋 Metadati: {os.path.abspath(METADATA_FILE)}")
        print(f"{'='*60}")
    
    except Exception as e:
        print(f"\n❌ Errore fatale: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
