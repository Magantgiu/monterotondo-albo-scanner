#!/usr/bin/env python3
import os, datetime as dt
from supabase import create_client, Client
from google.cloud import storage

ALBO_URL     = os.getenv("ALBO_URL")
SUP_URL      = os.getenv("SUPABASE_URL")
SUP_KEY      = os.getenv("SUPABASE_ANON_KEY")
GCS_BUCKET   = os.getenv("GCS_BUCKET")

def last_check_date() -> dt.date:
    sup: Client = create_client(SUP_URL, SUP_KEY)
    row = sup.table("atti").select("data_pubb").order("data_pubb", desc=True).limit(1).execute()
    return dt.datetime.fromisoformat(row.data[0]["data_pubb"]).date() if row.data else dt.date(2020,1,1)

def save_to_cloud(pdf_bytes, atto_id, data_pubb, oggetto):
    gcs = storage.Client()
    blob = gcs.bucket(GCS_BUCKET).blob(f"{data_pubb:%Y/%m}/{atto_id}.pdf")
    blob.upload_from_string(pdf_bytes, content_type="application/pdf")
    sup = create_client(SUP_URL, SUP_KEY)
    sup.table("atti").insert({
        "id": atto_id,
        "data_pubb": data_pubb.isoformat(),
        "oggetto": oggetto,
        "pdf_url": blob.public_url,
        "status": "new"
    }, upsert=True).execute()

# ---- importa il tuo script con le 23 iterazioni ----
import core_scraper

if __name__ == "__main__":
    since = last_check_date()
    print("🔍 cerco atti dal", since)
    for atto_id, data_pubb, oggetto, pdf_bytes in core_scraper.scarica_da(since):
        save_to_cloud(pdf_bytes, atto_id, data_pubb, oggetto)
        print("✅", atto_id)
