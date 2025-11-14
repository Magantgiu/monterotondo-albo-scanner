#!/usr/bin/env python3
"""
Cloud-ready wrapper:
- legge ultima data da Supabase
- scarica solo nuovi atti via core_scraper.scarica_da()
- upload PDF → Google Drive (per Apps Script)
- scrive metadati → Supabase (opzionale)
"""
import os
import datetime as dt
import io
from supabase import create_client, Client
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ---------- ENV ----------
SUP_URL      = os.getenv("SUPABASE_URL")
SUP_KEY      = os.getenv("SUPABASE_ANON_KEY")
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID")  # Cartella dove mettere i PDF
# -------------------------

def get_drive_service():
    """Autentica con Google Drive usando service account"""
    try:
        # Usa il file service_account.json (quello che hai nel repo)
        creds = Credentials.from_service_account_file(
            'gcs-key.json',
            scopes=['https://www.googleapis.com/auth/drive.file']
        )
        service = build('drive', 'v3', credentials=creds)
        print(f"📁 Google Drive autenticato")
        return service
    except Exception as e:
        print(f"❌ Errore autenticazione Drive: {e}")
        raise

def upload_to_drive(service, pdf_bytes: bytes, numero_atto: str, data_pubb: dt.date) -> str:
    """Upload PDF a Google Drive e ritorna il link"""
    try:
        # Crea il nome file
        filename = f"{numero_atto}_{data_pubb.isoformat()}.pdf"
        
        # Prepara il file
        file_metadata = {
            'name': filename,
            'parents': [DRIVE_FOLDER_ID],
            'mimeType': 'application/pdf'
        }
        
        media = MediaIoBaseUpload(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            resumable=True
        )
        
        print(f"  📤 Uploading a Drive: {filename}...")
        
        # Upload
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        
        file_id = file.get('id')
        file_link = file.get('webViewLink')
        
        print(f"  ✅ PDF su Drive: {file_link}")
        
        return file_link
    
    except Exception as e:
        print(f"  ❌ Errore upload Drive: {e}")
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
                              oggetto: str, drive_link: str):
    """Salva metadati in Supabase (opzionale)"""
    try:
        sup = create_client(SUP_URL, SUP_KEY)
        record = {
            "id": numero_atto,
            "data_pubb": data_pubb.isoformat(),
            "oggetto": oggetto,
            "pdf_url": drive_link,
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
    if not all([SUP_URL, SUP_KEY, DRIVE_FOLDER_ID]):
        print("❌ Variabili d'ambiente mancanti:")
        print(f"   SUPABASE_URL: {SUP_URL}")
        print(f"   SUPABASE_ANON_KEY: {'***' if SUP_KEY else 'MANCANTE'}")
        print(f"   DRIVE_FOLDER_ID: {DRIVE_FOLDER_ID}")
        exit(1)
    
    try:
        # Ottieni il servizio Drive
        drive_service = get_drive_service()
        
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
                
                # Upload a Google Drive
                drive_link = upload_to_drive(drive_service, pdf_bytes, atto_id, data_pubb)
                
                # Salva metadati in Supabase
                save_metadata_to_supabase(atto_id, data_pubb, oggetto, drive_link)
                
                print(f"     ✅ Completato!")
            
            except Exception as e:
                print(f"     ❌ Errore: {e}")
                continue
        
        print(f"\n{'='*60}")
        print(f"🎉 Completato! Scaricati {count} atti su Drive")
        print(f"{'='*60}")
    
    except Exception as e:
        print(f"\n❌ Errore fatale: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
