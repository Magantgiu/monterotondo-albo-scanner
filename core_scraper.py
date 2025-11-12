"""
core_scraper.py
Scarica atti da albo Hypersic (Monterotondo) – solo cloud-ready.
Pattern basato su versione Firefox funzionante
"""
import os
import datetime as dt
import time
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
# ----------------------------

def scarica_da(since: dt.date):
    """
    Generatore: per ogni atto con data >= since restituisce
    (id, data, oggetto, pdf_bytes)
    """
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    # Download automatico PDF
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
                    if not numero_atto.isdigit() or "NOT.ART. 140 C.P.C." in oggetto or not data_atto:
                        continue
                    
                    try:
                        data_pubb = dt.datetime.strptime(data_atto, "%d/%m/%Y").date()
                    except ValueError:
                        continue
                    
                    if data_pubb < since:
                        continue

                    print(f"🔍 Atto {numero_atto} ({data_pubb}): {oggetto[:50]}...")

                    # CLICK direttamente sulla cella (cells[4] = oggetto)
                    # Questo è quello che funziona nella versione Firefox
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
                        print(f"  📎 Trovati {len(all_links)} link")
                    except Exception as e:
                        print(f"  ⚠ Errore trovando link: {e}")
                        torna_alla_lista(driver, wait, LISTA_ATTI_BUTTON_ID)
                        continue

                    # CERCA IL PRIMO PDF CON "(Originale)"
                    pdf_trovato = False
                    for link_idx, link in enumerate(all_links):
                        try:
                            text = link.text.strip() or ""
                            text_clean = " ".join(text.split())
                            
                            # Controlla se è un PDF originale (non .p7m)
                            is_original_pdf = "(Originale)" in text_clean and ".p7m" not in text_clean.lower()
                            
                            if is_original_pdf:
                                print(f"  📥 PDF trovato: {text_clean[:60]}")
                                
                                # Scroll il link in vista
                                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                                time.sleep(0.5)
                                
                                # Click con JavaScript
                                driver.execute_script("arguments[0].click();", link)
                                time.sleep(4)
                                
                                # Leggi il PDF
                                files = sorted(
                                    [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)],
                                    key=os.path.getmtime,
                                    reverse=True,
                                )
                                if files:
                                    with open(files[0], "rb") as f:
                                        pdf_bytes = f.read()
                                    print(f"  ✅ PDF scaricato ({len(pdf_bytes)} bytes)")
                                    yield numero_atto, data_pubb, oggetto, pdf_bytes
                                    os.remove(files[0])
                                    pdf_trovato = True
                                break
                        except StaleElementReferenceException:
                            print(f"    ⚠ Link stale (#{link_idx})")
                            continue
                        except Exception as e:
                            print(f"    ⚠ Errore link {link_idx}: {e}")
                            continue

                    if not pdf_trovato:
                        print(f"  ⚠ Nessun PDF originale trovato")

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
