#!/usr/bin/env python3
"""
Cloud-ready wrapper:
- legge ultima data da Supabase
- scarica solo nuovi atti via core_scraper.scarica_da()
- upload PDF → GCS
- scrive metadati → Supabase
"""
import os
import datetime as dt
import json
from supabase import create_client, Client
from google.cloud import storage
from google.oauth2 import service_account

# ---------- ENV ----------
ALBO_URL     = os.getenv("ALBO_URL")
SUP_URL      = os.getenv("SUPABASE_URL")
SUP_KEY      = os.getenv("SUPABASE_ANON_KEY")
GCS_BUCKET   = os.getenv("GCS_BUCKET")
GCS_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # Path al JSON oppure JSON diretto
# -------------------------

def get_gcs_client():
    """Crea il client GCS con autenticazione corretta."""
    try:
        # Metodo 1: Se GOOGLE_APPLICATION_CREDENTIALS è un file path
        if GCS_CREDENTIALS and os.path.isfile(GCS_CREDENTIALS):
            print(f"📋 Usando credenziali da file: {GCS_CREDENTIALS}")
            return storage.Client()
        
        # Metodo 2: Se GOOGLE_APPLICATION_CREDENTIALS è il JSON diretto
        if GCS_CREDENTIALS:
            creds_dict = json.loads(GCS_CREDENTIALS)
            credentials = service_account.Credentials.from_service_account_info(creds_dict)
            print(f"📋 Usando credenziali da env JSON")
            return storage.Client(credentials=credentials)
        
        # Metodo 3: Fallback a credenziali default (ADC - Application Default Credentials)
        print(f"📋 Usando Application Default Credentials")
        return storage.Client()
    
    except Exception as e:
        print(f"❌ Errore creando GCS client: {e}")
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

def save_to_cloud(pdf_bytes: bytes, atto_id: str, data_pubb: dt.date, oggetto: str) -> str:
    """Upload PDF su GCS e salva metadati su Supabase."""
    try:
        # Upload su GCS
        gcs = get_gcs_client()
        bucket = gcs.bucket(GCS_BUCKET)
        blob_path = f"{data_pubb:%Y/%m}/{atto_id}.pdf"
        blob = bucket.blob(blob_path)
        
        print(f"  📤 Uploading to GCS: {blob_path}...")
        blob.upload_from_string(pdf_bytes, content_type="application/pdf")
        
        # NON usiamo blob.make_public() se il bucket ha uniform access
        # Generiamo l'URL pubblico direttamente
        public_url = f"https://storage.googleapis.com/{GCS_BUCKET}/{blob_path}"
        print(f"  ✅ Upload completato: {public_url}")
        
        # Salva metadati su Supabase
        sup = create_client(SUP_URL, SUP_KEY)
        record = {
            "id": atto_id,
            "data_pubb": data_pubb.isoformat(),
            "oggetto": oggetto,
            "pdf_url": public_url,
            "status": "new"
        }
        
        sup.table("atti").insert(record, upsert=True).execute()
        print(f"  ✅ Metadati salvati su Supabase")
        
        return public_url
    
    except Exception as e:
        print(f"  ❌ Errore: {e}")
        raise

# ---------- MAIN ----------
if __name__ == "__main__":
    print("🚀 Inizio scaricamento atti...\n")
    
    # Validazione env
    if not all([SUP_URL, SUP_KEY, GCS_BUCKET]):
        print("❌ Variabili d'ambiente mancanti:")
        print(f"   SUPABASE_URL: {SUP_URL}")
        print(f"   SUPABASE_ANON_KEY: {'***' if SUP_KEY else 'MANCANTE'}")
        print(f"   GCS_BUCKET: {GCS_BUCKET}")
        exit(1)
    
    if not GCS_CREDENTIALS:
        print("⚠ GOOGLE_APPLICATION_CREDENTIALS non impostato, userò ADC...")
    
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
                
                url = save_to_cloud(pdf_bytes, atto_id, data_pubb, oggetto)
                print(f"     ✅ Salvato: {url}")
            
            except Exception as e:
                print(f"     ❌ Errore salvando: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"🎉 Completato! Scaricati {count} atti")
        print(f"{'='*60}")
    
    except Exception as e:
        print(f"\n❌ Errore fatale: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
