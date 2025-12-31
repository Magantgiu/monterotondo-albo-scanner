"""
core_scraper.py
Scarica atti da albo Hypersic (Monterotondo) – solo cloud-ready.
Scarica TUTTI i PDF seguendo i reindirizzamenti getfile.aspx
"""
import os
import datetime as dt
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, StaleElementReferenceException
from urllib.parse import urlparse, parse_qs
import io

# ---------- CONFIG ----------
TABLE_ID = "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_risultati_tab_risultati_table"
ALLEGATI_PANEL_ID = "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_dettaglio_tab_dettaglio_sidebar_allegati_tab_dettaglio_sidebar_allegati_pnl"
LISTA_ATTI_BUTTON_ID = "tab_pnlnav_tab_risultati"
# ----------------------------

def get_pdf_from_getfile_url(driver, getfile_url: str) -> bytes:
    """
    Segue il reindirizzamento da getfile.aspx al PDF vero.
    Estrae PARAM e KEY dall'URL e scarica il PDF.
    """
    try:
        print(f"    🔗 Seguendo reindirizzamento: {getfile_url[:80]}...")
        
        # Usa requests per seguire i reindirizzamenti e ottenere il PDF
        session = requests.Session()
        
        # Copia i cookie da Selenium a requests
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        
        response = session.get(getfile_url, allow_redirects=True, timeout=30)
        
        if response.status_code == 200 and len(response.content) > 0:
            print(f"    ✅ PDF scaricato ({len(response.content)} bytes)")
            return response.content
        else:
            print(f"    ⚠ Risposta non valida: {response.status_code}")
            return None
    
    except Exception as e:
        print(f"    ⚠ Errore seguendo URL: {e}")
        return None

def scarica_da(since: dt.date):
    """
    Generatore: per ogni atto con data >= since restituisce
    (id, data, oggetto, pdf_bytes)
    Scarica TUTTI i PDF allegati (esclusi .p7m)
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    # Download automatico PDF (se usato)
    tmp_dir = os.path.abspath("./tmp_pdf")
    os.makedirs(tmp_dir, exist_ok=True)
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": tmp_dir,
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True,
        },
    )

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)
    
    try:
        base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo"
        albo_url = f"{base_url}/portale/albopretorio/albopretorioconsultazione.aspx?P=400"
        driver.get(os.getenv("ALBO_URL", albo_url))
        print(f"📄 Caricamento: {os.getenv('ALBO_URL', albo_url)}")

        # Chiudi cookie banner
        for txt in ("Accetto", "ACCETTO", "Accetta", "Accept"):
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH, f"//button[contains(text(), '{txt}')]")))
                driver.execute_script("arguments[0].click();", btn)
                print("✓ Cookie banner chiuso")
                time.sleep(1)
                break
            except TimeoutException:
                continue

        page = 1
        while page <= 3:
            print(f"\n📖 Pagina {page}")
            
            # Attendi tabella
            try:
                wait.until(EC.presence_of_element_located((By.ID, TABLE_ID)))
            except TimeoutException:
                print("✗ Tabella non trovata")
                break
            
            time.sleep(2)

            # Estrai righe dalla tabella
            try:
                table_container = driver.find_element(By.ID, TABLE_ID)
                table = table_container.find_element(By.TAG_NAME, "table")
                rows = table.find_elements(By.XPATH, ".//tbody/tr")
                print(f"📊 Trovate {len(rows)} righe")
            except Exception as e:
                print(f"✗ Errore estraendo righe: {e}")
                break

            # Per ogni riga, elabora
            for row_idx in range(len(rows)):
                try:
                    # RICARICARE le righe ogni volta
                    table_container = driver.find_element(By.ID, TABLE_ID)
                    table = table_container.find_element(By.TAG_NAME, "table")
                    rows = table.find_elements(By.XPATH, ".//tbody/tr")
                    
                    if row_idx >= len(rows):
                        continue
                    
                    row = rows[row_idx]
                    cells = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cells) < 8:
                        continue
                    
                    numero_atto = cells[3].text.strip()
                    data_atto = cells[7].text.strip()
                    oggetto = cells[4].text.strip()
                    
                    # Salta righe non valide
                    if not numero_atto.isdigit() or not data_atto:
                        continue
                    
                    try:
                        data_pubb = dt.datetime.strptime(data_atto, "%d/%m/%Y").date()
                    except ValueError:
                        continue
                    
                    if data_pubb < since:
                        continue

                    print(f"🔍 Atto {numero_atto} ({data_pubb}): {oggetto[:50]}...")

                    # CLICK direttamente sulla cella
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cells[4])
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", cells[4])
                    time.sleep(3)

                    # Attendi allegati
                    try:
                        wait.until(EC.presence_of_element_located((By.ID, ALLEGATI_PANEL_ID)))
                    except TimeoutException:
                        print(f"  ⚠ Panel allegati non trovato")
                        torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)
                        continue

                    # Estrai i link dal panel allegati
                    try:
                        allegati_panel = driver.find_element(By.ID, ALLEGATI_PANEL_ID)
                        all_links = allegati_panel.find_elements(By.XPATH, ".//a")
                        print(f"  📎 Trovati {len(all_links)} allegati")
                    except Exception as e:
                        print(f"  ⚠ Errore trovando link: {e}")
                        torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)
                        continue

                    # SCARICA TUTTI I PDF (escludi .p7m)
                    allegati_scaricati = 0
                    for link_idx, link in enumerate(all_links):
                        try:
                            text = link.text.strip() or ""
                            text_clean = " ".join(text.split())
                            
                            # Salta i file .p7m
                            if ".p7m" in text_clean.lower():
                                print(f"  ⏭ Saltato: {text_clean[:50]} (.p7m)")
                                continue
                            
                            # Ottieni l'href del link
                            href = link.get_attribute("href") or ""
                            
                            if not href:
                                print(f"  ⚠ Link {link_idx}: nessun href")
                                continue
                            
                            # Costruisci l'URL completo se relativo
                            if href.startswith("http"):
                                full_url = href
                            else:
                                full_url = f"https://servizionline.hspromilaprod.hypersicapp.net{href}"
                            
                            print(f"  📥 [{link_idx+1}] {text_clean[:60]}...")
                            print(f"      URL: {full_url[:80]}...")
                            
                            # Scarica il PDF seguendo il reindirizzamento
                            pdf_bytes = get_pdf_from_getfile_url(driver, full_url)
                            
                            if pdf_bytes and len(pdf_bytes) > 0:
                                yield numero_atto, data_pubb, oggetto, pdf_bytes
                                allegati_scaricati += 1
                            
                        except StaleElementReferenceException:
                            print(f"  ⚠ Link stale (#{link_idx})")
                            continue
                        except Exception as e:
                            print(f"  ⚠ Errore link {link_idx}: {e}")
                            continue

                    print(f"  ✅ Allegati scaricati per questo atto: {allegati_scaricati}")

                    # Torna alla lista
                    torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)

                except StaleElementReferenceException:
                    print(f"  ✗ Elemento stale")
                    torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)
                except Exception as e:
                    print(f"  ✗ Errore: {e}")
                    torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)

            # Prossima pagina
            try:
                next_btn = driver.find_element(By.LINK_TEXT, str(page + 1))
                next_btn.click()
                page += 1
                time.sleep(3)
            except:
                break

    finally:
        driver.quit()
        print("\n✓ Browser chiuso")


def torna_alla_lista(driver, wait, lista_btn_id):
    """Torna alla lista"""
    try:
        back_btn = wait.until(EC.element_to_be_clickable((By.ID, lista_btn_id)))
        driver.execute_script("arguments[0].click();", back_btn)
        time.sleep(2)
    except Exception as e:
        print(f"  ⚠ Errore tornando: {e}")
        time.sleep(1)
