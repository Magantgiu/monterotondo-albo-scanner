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
    return dt.datetime.fromisoformat(row.data[0]["data_pubb"]).date() if row.data else dt.date(2025,11,1)

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

import time
import sqlite3
import pandas as pd
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# COSTANTI
ALBO_TABLE_CONTAINER_ID = "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_risultati_tab_risultati_table"
LISTA_ATTI_BUTTON_ID = "tab_pnlnav_tab_risultati"
ALLEGATI_PANEL_ID = "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_dettaglio_tab_dettaglio_sidebar_allegati_tab_dettaglio_sidebar_allegati_pnl"

class AlboDetailedExtractor:
    def __init__(self, download_dir="./albo_pdf_downloads", headless=False):
        self.base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo"
        self.albo_url = f"{self.base_url}/portale/albopretorio/albopretorioconsultazione.aspx?P=400"
        self.db_path = "albo_dettagli_completo.db"
        self.download_dir = download_dir
        self.max_pages = 2
        self.headless = headless
        
        os.makedirs(self.download_dir, exist_ok=True)
        self.init_database()

    def init_database(self):
        """Inizializza il database SQLite."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Controlla se la tabella esiste e ha la colonna file_locale
            cursor.execute("PRAGMA table_info(atti)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'file_locale' not in columns:
                logger.warning(f"⚠️ Tabella vecchia rilevata, la ricreo...")
                cursor.execute("DROP TABLE IF EXISTS atti")
                conn.commit()
            
            # Crea la tabella (se non esiste)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS atti (
                    numero_atto TEXT,
                    data_atto TEXT,
                    tipo_atto TEXT,
                    oggetto TEXT,
                    page_num INTEGER,
                    position INTEGER,
                    url_download TEXT,
                    nome_documento TEXT,
                    file_locale TEXT,
                    scaricato INTEGER DEFAULT 0,
                    PRIMARY KEY (numero_atto, nome_documento)
                )
            ''')
            conn.commit()
            logger.info("✅ Database inizializzato correttamente")
            conn.close()
        except Exception as e:
            logger.error(f"❌ Errore inizializzazione DB: {e}")

    def setup_firefox(self):
        """Setup Chrome con opzioni ottimizzate."""
        options = Options()
        
        if self.headless:
            options.add_argument("--headless")
            logger.info("🖥️ Chrome in modalità HEADLESS")
        
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # ✅ Configura il download automatico
        options.set_preference("browser.download.folderList", 2)  # 0=Desktop, 1=Downloads, 2=Custom
        options.set_preference("browser.download.manager.showWhenStarting", False)
        options.set_preference("browser.download.dir", os.path.abspath(self.download_dir))
        options.set_preference("browser.helperApps.neverAsk.saveToDisk", "application/pdf,application/x-pdf")
        options.set_preference("pdfjs.disabled", True)  # Disabilita PDF viewer interno
        
        logger.info(f"📁 Download directory: {os.path.abspath(self.download_dir)}")
        
        try:
            driver = webdriver.chrome(options=options)
            driver.current_page = 1
            return driver
        except Exception as e:
            logger.error(f"Errore inizializzazione Firefox: {e}")
            raise

    def handle_cookies(self, driver):
        """Chiude il banner cookie - versione robusta."""
        cookie_selectors = [
            (By.ID, "CybotCookiebotDialogBodyLevelButtonLevelPage"),
            (By.XPATH, "//button[contains(text(), 'Accetto')]"),
            (By.XPATH, "//button[contains(text(), 'ACCETTO')]"),
            (By.XPATH, "//button[contains(text(), 'Accetti')]"),
            (By.XPATH, "//button[contains(text(), 'Accetta')]"),
        ]
        
        try:
            wait = WebDriverWait(driver, 8)
            for selector_type, selector_value in cookie_selectors:
                try:
                    cookie_btn = wait.until(EC.element_to_be_clickable((selector_type, selector_value)))
                    driver.execute_script("arguments[0].click();", cookie_btn)
                    logger.info(f"✅ Cookie gestiti")
                    time.sleep(2)
                    break
                except TimeoutException:
                    continue
        except Exception as e:
            logger.warning(f"⚠️ Errore handling cookies: {e}")

    def parse_atto_row(self, row, row_index):
        """Estrae i dati da una riga della tabella."""
        cells = row.find_elements(By.TAG_NAME, "td")
        
        if len(cells) < 4:
            return None
        
        numero_atto = cells[3].text.strip() if len(cells) > 3 else "N/A"
        oggetto = cells[4].text.strip() if len(cells) > 4 else "N/A"
        tipo_atto = cells[5].text.strip() if len(cells) > 5 else "N/A"
        data_atto = cells[7].text.strip() if len(cells) > 7 else "N/A"
        
        if not numero_atto or numero_atto.lower() in ['numero', 'numero atto', 'atto']:
            return None
        
        try:
            int(numero_atto)
        except ValueError:
            return None
        
        # ✅ FILTRO: Salta gli atti "NOT.ART. 140 C.P.C." che non hanno allegati
        if "NOT.ART. 140 C.P.C." in oggetto:
            logger.info(f"      ⏭️ Row {row_index}: Saltato (NOT.ART. 140 C.P.C. - senza allegati)")
            return None
        
        # Cerca link cliccabile
        clickable_element = cells[4]  # La cella è direttamente cliccabile
        
        logger.info(f"      ✅ Row {row_index}: {numero_atto} | {oggetto[:40]}")

        return {
            'numero_atto': numero_atto,
            'data_atto': data_atto,
            'tipo_atto': tipo_atto,
            'oggetto': oggetto,
            'row_index': row_index,
            'clickable_element': clickable_element
        }

    def extract_atti_list_from_page(self, driver):
        """Estrae lista atti dalla pagina corrente."""
        atti_list = []
        
        try:
            wait = WebDriverWait(driver, 20)
            
            logger.info(f"  🔍 Cercando container...")
            table_container = wait.until(
                EC.presence_of_element_located((By.ID, ALBO_TABLE_CONTAINER_ID))
            )
            logger.info(f"  ✅ Container trovato")
            
            time.sleep(2)
            
            try:
                table = table_container.find_element(By.TAG_NAME, "table")
                rows = table.find_elements(By.XPATH, ".//tbody/tr")
            except:
                rows = []
            
            if not rows:
                logger.warning("  ⚠️ Nessuna riga trovata")
                return atti_list
            
            logger.info(f"  ✅ Trovate {len(rows)} righe")
            
            for idx, row in enumerate(rows):
                try:
                    atto_info = self.parse_atto_row(row, idx)
                    if atto_info and atto_info.get('clickable_element'):
                        atti_list.append(atto_info)
                except Exception as e:
                    logger.debug(f"    Row {idx}: Errore: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"  ❌ Errore: {e}")
            
        return atti_list

    def extract_documents_from_detail_page(self, driver, atto_info, page_num, position):
        """Estrae il primo PDF valido dalla pagina di dettaglio."""
        documento = None
        
        try:
            wait = WebDriverWait(driver, 10)
            allegati_panel = wait.until(
                EC.presence_of_element_located((By.ID, ALLEGATI_PANEL_ID))
            )
            
            all_links = allegati_panel.find_elements(By.XPATH, ".//a")
            logger.info(f"    Trovati {len(all_links)} link negli allegati")
            
            # PRENDI IL PRIMO PDF CON "(Originale)"
            for idx, link in enumerate(all_links):
                try:
                    text = link.text.strip() or ""
                    text_clean = " ".join(text.split())  # Rimuovi newline e spazi extra
                    
                    # I PDF originali hanno "(Originale)" nel testo, i .p7m hanno ".p7m"
                    is_pdf = ('(Originale)' in text_clean and '.p7m' not in text_clean.lower())
                    
                    if is_pdf:
                        logger.info(f"    ✅ PDF trovato: {text_clean[:60]}")
                        
                        # Genera nome file sicuro
                        safe_filename = f"{atto_info['numero_atto'].replace('/', '-')}_{text_clean}".replace(' ', '_')
                        safe_filename = "".join(c for c in safe_filename if c not in '<>:"|?*\n')
                        if not safe_filename.endswith('.pdf'):
                            safe_filename += '.pdf'
                        
                        logger.info(f"    🖱️ Clicco il link per scaricare...")
                        
                        # Clicca il link - Firefox scarica automaticamente
                        link.click()
                        time.sleep(3)  # Attendi il download
                        
                        # Verifica che il file esista
                        filepath = os.path.join(self.download_dir, safe_filename)
                        if os.path.exists(filepath):
                            logger.info(f"    ✅ File scaricato: {safe_filename}")
                        else:
                            # Prova con il file più recente
                            files = sorted(os.listdir(self.download_dir), 
                                         key=lambda f: os.path.getmtime(os.path.join(self.download_dir, f)),
                                         reverse=True)
                            if files:
                                filepath = os.path.join(self.download_dir, files[0])
                                logger.info(f"    ✅ File più recente: {files[0]}")
                            else:
                                filepath = None
                        
                        if filepath:
                            documento = {
                                'numero_atto': atto_info['numero_atto'],
                                'data_atto': atto_info['data_atto'],
                                'tipo_atto': atto_info['tipo_atto'],
                                'oggetto': atto_info['oggetto'],
                                'page_num': page_num,
                                'position': position,
                                'url_download': 'getfile.asp (click)',
                                'nome_documento': text_clean,
                                'file_locale': filepath,
                                'scaricato': 1
                            }
                        break
                    
                except Exception as e:
                    logger.error(f"      Link {idx}: Errore: {e}")
                    continue
            
            if not documento:
                logger.info(f"    ⚠️ Nessun PDF trovato")
                
        except Exception as e:
            logger.error(f"    Errore: {e}")
            
        return documento

    def extract_atto_details(self, driver, atto_info, page_num, position):
        """Naviga nel dettaglio e estrae i dati."""
        try:
            wait = WebDriverWait(driver, 15)
            
            row_index = atto_info['row_index']
            xpath = f"//*[@id='{ALBO_TABLE_CONTAINER_ID}']/div/div/table/tbody/tr[{row_index + 1}]/td[5]"
            
            logger.info(f"    🖱️ Clicco su atto {atto_info['numero_atto']}...")
            clickable = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", clickable)
            time.sleep(1)
            clickable.click()
            
            logger.info(f"    ⏳ Attendo caricamento dettaglio...")
            time.sleep(3)
            
            # Attendi panel allegati
            try:
                wait.until(EC.presence_of_element_located((By.ID, ALLEGATI_PANEL_ID)))
            except:
                logger.warning(f"    ⚠️ Panel allegati non trovato")
                return None
            
            documento = self.extract_documents_from_detail_page(driver, atto_info, page_num, position)
            
            logger.info(f"    ↩️ Torno alla lista...")
            try:
                lista_btn = wait.until(EC.element_to_be_clickable((By.ID, LISTA_ATTI_BUTTON_ID)))
                driver.execute_script("arguments[0].click();", lista_btn)
            except:
                logger.warning(f"      Ricarico pagina...")
                driver.get(self.albo_url)
                self.handle_cookies(driver)
            
            wait.until(EC.presence_of_element_located((By.ID, ALBO_TABLE_CONTAINER_ID)))
            time.sleep(2)
            
            return documento
            
        except Exception as e:
            logger.error(f"    ❌ Errore: {e}")
            return None

    def navigate_to_next_page(self, driver):
        """Naviga alla pagina successiva."""
        current_page = driver.current_page
        next_page = current_page + 1
        
        try:
            wait = WebDriverWait(driver, 5)
            next_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, str(next_page))))
            driver.execute_script("arguments[0].click();", next_link)
            wait.until(EC.presence_of_element_located((By.ID, ALBO_TABLE_CONTAINER_ID)))
            driver.current_page = next_page
            logger.info(f"    ➡️ Pagina {next_page}")
            return True
        except:
            logger.info(f"    📄 Fine pagine")
            return False

    def save_atti_batch(self, atti_list):
        """Salva nel database."""
        if not atti_list:
            logger.warning("    ⚠️ Nessun documento da salvare")
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            insert_query = """
                INSERT OR REPLACE INTO atti 
                (numero_atto, data_atto, tipo_atto, oggetto, page_num, position, url_download, nome_documento, file_locale, scaricato)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            for a in atti_list:
                try:
                    data = (
                        a['numero_atto'], 
                        a['data_atto'], 
                        a['tipo_atto'], 
                        a['oggetto'], 
                        a['page_num'], 
                        a['position'], 
                        a['url_download'], 
                        a['nome_documento'],
                        a.get('file_locale', ''), 
                        a.get('scaricato', 0)
                    )
                    cursor.execute(insert_query, data)
                    logger.debug(f"      ✅ Salvato: {a['numero_atto']} - {a['nome_documento'][:40]}")
                except Exception as e:
                    logger.error(f"      ❌ Errore salvataggio {a['numero_atto']}: {e}")
            
            conn.commit()
            logger.info(f"    💾 Salvati {len(atti_list)} documenti nel DB")
            conn.close()
            
        except Exception as e:
            logger.error(f"    ❌ Errore connessione DB: {e}")

    def export_results(self):
        """Esporta in CSV."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Conta quanti record ci sono nel DB
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM atti")
            count = cursor.fetchone()[0]
            logger.info(f"📊 Record nel database: {count}")
            
            # Leggi i record
            df = pd.read_sql_query("SELECT * FROM atti", conn)
            
            if len(df) == 0:
                logger.warning(f"⚠️ Nessun record nel database da esportare")
                return
            
            # Salva CSV
            df.to_csv("risultati_albo_pretorio.csv", index=False, encoding='utf-8')
            logger.info(f"🎉 CSV esportato: risultati_albo_pretorio.csv ({len(df)} righe)")
            logger.info(f"📁 PDF scaricati in: {self.download_dir}")
            
            # Mostra preview del CSV
            logger.info("\n📋 Preview risultati:")
            for idx, row in df.iterrows():
                logger.info(f"  {row['numero_atto']} - {row['nome_documento'][:50]} - {row['file_locale']}")
            
        except Exception as e:
            logger.error(f"❌ Errore export: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            try:
                conn.close()
            except:
                pass

    def run_scraper(self):
        """Ciclo principale."""
        driver = None
        try:
            driver = self.setup_firefox()
            driver.get(self.albo_url)
            self.handle_cookies(driver)
            
            current_page = 1
            total_docs = 0

            while current_page <= self.max_pages:
                logger.info(f"\n*** 🌐 Pagina {current_page} / {self.max_pages} ***")
                
                atti = self.extract_atti_list_from_page(driver)
                logger.info(f"    -> Trovati {len(atti)} atti")

                docs_batch = []
                
                for pos, atto in enumerate(atti):
                    logger.info(f"    -> Atto {pos+1}/{len(atti)}: {atto['numero_atto']}")
                    doc = self.extract_atto_details(driver, atto, current_page, pos + 1)
                    
                    if doc:
                        docs_batch.append(doc)
                    
                    time.sleep(1)

                if docs_batch:
                    self.save_atti_batch(docs_batch)
                    total_docs += len(docs_batch)

                if current_page < self.max_pages and self.navigate_to_next_page(driver):
                    current_page += 1
                    time.sleep(3)
                else:
                    break
            
            logger.info(f"\n*** ✅ Completato: {total_docs} documenti ***")
            self.export_results()

        except Exception as e:
            logger.critical(f"🛑 Errore: {e}")
        finally:
            if driver:
                driver.quit()

if __name__ == '__main__':
    scraper = AlboDetailedExtractor(headless=False)
    scraper.run_scraper()


import core_scraper

if __name__ == "__main__":
    since = last_check_date()
    print("🔍 cerco atti dal", since)
    for atto_id, data_pubb, oggetto, pdf_bytes in core_scraper.scarica_da(since):
        save_to_cloud(pdf_bytes, atto_id, data_pubb, oggetto)
        print("✅", atto_id)
