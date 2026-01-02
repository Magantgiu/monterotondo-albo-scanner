"""
core_scraper.py - Versione LOCALE
Scarica atti da albo Hypersic (Monterotondo)
Salva PDF in cartella locale
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

# ---------- CONFIG ----------
TABLE_ID = "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_risultati_tab_risultati_table"
ALLEGATI_PANEL_ID = "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_dettaglio_tab_dettaglio_sidebar_allegati_tab_dettaglio_sidebar_allegati_pnl"
LISTA_ATTI_BUTTON_ID = "tab_pnlnav_tab_risultati"

# Indici colonne corretti
COL_NUMERO = 4      # numero atto
COL_OGGETTO = 5     # descrizione
COL_DATA = 8        # data pubblicazione
# ----------------------------

def get_pdf_from_getfile_url(driver, getfile_url: str) -> bytes:
    """Scarica PDF seguendo i reindirizzamenti"""
    try:
        print(f"    🔗 Scaricando: {getfile_url[:60]}...")
        
        session = requests.Session()
        
        # Copia i cookie da Selenium a requests
        for cookie in driver.get_cookies():
            try:
                session.cookies.set(cookie['name'], cookie['value'])
            except:
                pass
        
        response = session.get(getfile_url, allow_redirects=True, timeout=30)
        
        if response.status_code == 200 and len(response.content) > 0:
            print(f"    ✅ Scaricato ({len(response.content)} bytes)")
            return response.content
        else:
            print(f"    ⚠ Errore HTTP {response.status_code}")
            return None
    
    except Exception as e:
        print(f"    ⚠ Errore: {e}")
        return None

def scarica_da(since: dt.date):
    """
    Generatore che scarica atti da Hypersic
    Yield: (numero_atto, data_pubb, oggetto, pdf_bytes, allegato_num)
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 15)
    
    try:
        base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo"
        albo_url = f"{base_url}/portale/albopretorio/albopretorioconsultazione.aspx?P=400"
        
        print(f"📄 Caricamento: {albo_url}")
        driver.get(albo_url)
        time.sleep(5)

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
        while page <= 10:
            print(f"\n📖 Pagina {page}")
            
            # Attendi tabella
            try:
                wait.until(EC.presence_of_element_located((By.ID, TABLE_ID)))
            except TimeoutException:
                print("✗ Tabella non trovata")
                break
            
            time.sleep(2)

            # Estrai righe
            try:
                table_container = driver.find_element(By.ID, TABLE_ID)
                table = table_container.find_element(By.TAG_NAME, "table")
                rows = table.find_elements(By.XPATH, ".//tbody/tr")
                print(f"📊 Trovate {len(rows)} righe")
                
                if len(rows) == 0:
                    break
                    
            except Exception as e:
                print(f"✗ Errore: {e}")
                break

            # Elabora ogni riga
            for row_idx in range(len(rows)):
                try:
                    # Ricarica le righe ogni volta
                    table_container = driver.find_element(By.ID, TABLE_ID)
                    table = table_container.find_element(By.TAG_NAME, "table")
                    rows = table.find_elements(By.XPATH, ".//tbody/tr")
                    
                    if row_idx >= len(rows):
                        continue
                    
                    row = rows[row_idx]
                    cells = row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cells) < 10:
                        print(f"  ⚠ Riga {row_idx}: meno di 10 celle")
                        continue
                    
                    # Estrai dati dalle colonne corrette
                    numero_atto = cells[COL_NUMERO].text.strip()
                    oggetto = cells[COL_OGGETTO].text.strip()
                    data_str = cells[COL_DATA].text.strip()
                    
                    # Validazioni
                    if not numero_atto or not data_str:
                        continue
                    
                    # ESCLUDE atti con "F.to" nel testo
                    if "F.to" in oggetto or "F.to" in numero_atto:
                        print(f"  ⏭ Saltato (contiene F.to): {numero_atto}")
                        continue
                    
                    try:
                        data_pubb = dt.datetime.strptime(data_str, "%d/%m/%Y").date()
                    except ValueError:
                        continue
                    
                    if data_pubb < since:
                        print(f"  ⏭ Saltato (data < {since}): {numero_atto} ({data_pubb})")
                        continue

                    print(f"🔍 Atto {numero_atto} ({data_pubb}): {oggetto[:60]}...")

                    # CLICK sulla riga (cliccherà la prima cella)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cells[0])
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", cells[0])
                    time.sleep(3)

                    # Attendi panel allegati
                    try:
                        wait.until(EC.presence_of_element_located((By.ID, ALLEGATI_PANEL_ID)))
                    except TimeoutException:
                        print(f"  ⚠ Allegati non trovati")
                        torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)
                        continue

                    # Estrai link allegati
                    try:
                        allegati_panel = driver.find_element(By.ID, ALLEGATI_PANEL_ID)
                        all_links = allegati_panel.find_elements(By.XPATH, ".//a")
                        print(f"  📎 {len(all_links)} allegati")
                    except Exception as e:
                        print(f"  ⚠ Errore trovando link: {e}")
                        torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)
                        continue

                    # Scarica PDF
                    allegati_count = 0
                    for link_idx, link in enumerate(all_links):
                        try:
                            text = link.text.strip() or ""
                            
                            # Salta .p7m
                            if ".p7m" in text.lower():
                                continue
                            
                            href = link.get_attribute("href") or ""
                            
                            if not href:
                                continue
                            
                            if href.startswith("http"):
                                full_url = href
                            else:
                                full_url = f"https://servizionline.hspromilaprod.hypersicapp.net{href}"
                            
                            print(f"  📥 {text[:50]}...")
                            
                            pdf_bytes = get_pdf_from_getfile_url(driver, full_url)
                            
                            if pdf_bytes and len(pdf_bytes) > 0:
                                allegati_count += 1
                                yield numero_atto, data_pubb, oggetto, pdf_bytes, allegati_count
                            
                        except StaleElementReferenceException:
                            continue
                        except Exception as e:
                            print(f"  ⚠ Errore link: {e}")
                            continue

                    print(f"  ✅ {allegati_count} file scaricati")
                    torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)

                except StaleElementReferenceException:
                    torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)
                except Exception as e:
                    print(f"  ✗ Errore: {e}")
                    torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)

            # Prossima pagina
            try:
                print(f"  📄 Cercando pagina {page + 1}...")
                next_btn = wait.until(
                    EC.element_to_be_clickable((By.LINK_TEXT, str(page + 1)))
                )
                print(f"  📄 Trovata pagina {page + 1}, cliccando...")
                driver.execute_script("arguments[0].click();", next_btn)
                page += 1
                time.sleep(4)  # Aspetta il caricamento
            except TimeoutException:
                print("✓ Fine pagine")
                break
            except Exception as e:
                print(f"✗ Errore navigazione: {e}")
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
    except:
        time.sleep(1)
