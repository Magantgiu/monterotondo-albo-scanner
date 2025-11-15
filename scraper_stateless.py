#!/usr/bin/env python3
"""
Cloud-ready wrapper:
- legge ultima data da Supabase
- scarica solo nuovi atti via core_scraper.scarica_da()
- salva PDF in cartella locale /pdfs
- scrive metadati → Supabase
"""
import os
import datetime as dt
from supabase import create_client, Client

# ---------- ENV ----------
SUP_URL      = os.getenv("SUPABASE_URL")
SUP_KEY      = os.getenv("SUPABASE_KEY")
PDF_FOLDER   = "./pdfs"  # Cartella locale
# -------------------------

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

def last_check_date() -> dt.date:
    """Ultima data già salvata (o 1 nov 2025 se vuoto)."""
    try:
        sup: Client = create_client(SUP_URL, SUP_KEY)
        row = sup.table("atti").select("data_pubb").order("data_pubb", desc=True).limit(1).execute()
        
        if row.data and len(row.data) > 0:
            date_str = row.data[0]["data_pubb"]
            return dt.datetime.fromisoformat(date_str).date()
        else:
            print("⚠ Nessun atto trovato in Supabase, scarico da 1 nov 2025")
            return dt.date(2025, 11, 1)
    except Exception as e:
        print(f"⚠ Errore leggendo da Supabase: {e}")
        return dt.date(2025, 11, 1)

def save_metadata_to_supabase(numero_atto: str, data_pubb: dt.date, 
                              oggetto: str, pdf_path: str):
    """Salva metadati in Supabase"""
    try:
        sup = create_client(SUP_URL, SUP_KEY)
        record = {
            "id": numero_atto,
            "data_pubb": data_pubb.isoformat(),
            "oggetto": oggetto,
            "pdf_url": pdf_path,
            "status": "nuovo"
        }
        
        sup.table("atti").insert(record, upsert=True).execute()
        print(f"  ✅ Metadati salvati in Supabase")
        
    except Exception as e:
        print(f"  ⚠ Errore salvando metadati: {e}")

# ---------- MAIN ----------
if __name__ == "__main__":
    print("🚀 Inizio scaricamento atti...\n")
    
    # Validazione env
    if not all([SUP_URL, SUP_KEY]):
        print("❌ Variabili d'ambiente mancanti:")
        print(f"   SUPABASE_URL: {SUP_URL}")
        print(f"   SUPABASE_KEY: {'***' if SUP_KEY else 'MANCANTE'}")
        exit(1)
    
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
                
                # Salva metadati in Supabase
                save_metadata_to_supabase(atto_id, data_pubb, oggetto, pdf_path)
                
                print(f"     ✅ Completato!")
            
            except Exception as e:
                print(f"     ❌ Errore: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"🎉 Completato! Scaricati {count} atti")
        print(f"📁 Cartella: {os.path.abspath(PDF_FOLDER)}/")
        print(f"{'='*60}")
    
    except Exception as e:
        print(f"\n❌ Errore fatale: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
