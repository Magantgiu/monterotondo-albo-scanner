"""
core_scraper.py
Scarica atti da albo Hypersic (Monterotondo) – solo cloud-ready.
Pattern basato su UIVision RPA automation
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
BACK_TAB_ID = "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab"
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

            # Estrai righe dalla tabella usando lo XPath esatto di UIVision
            try:
                # Questo XPath corrisponde a: #table/div/div/table/tbody/tr
                row_xpath = f"//*[@id='{TABLE_ID}']/div/div/table/tbody/tr"
                rows = driver.find_elements(By.XPATH, row_xpath)
                print(f"📊 Trovate {len(rows)} righe")
            except Exception as e:
                print(f"✗ Errore estraendo righe: {e}")
                break

            # Per ogni riga, elabora
            for row_num in range(1, len(rows) + 1):
                try:
                    # Ricaricare ogni volta per evitare stale elements
                    rows = driver.find_elements(By.XPATH, row_xpath)
                    
                    if row_num > len(rows):
                        continue
                    
                    row = rows[row_num - 1]  # Gli indici partono da 0, ma gli XPath da 1
                    
                    # Estrai dati dalla riga
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

                    # CLICK sulla riga (colonna 5 = oggetto)
                    # XPath: //*[@id="table"]/div/div/table/tbody/tr[N]/td[5]
                    click_xpath = f"//*[@id='{TABLE_ID}']/div/div/table/tbody/tr[{row_num}]/td[5]"
                    try:
                        el = wait.until(EC.element_to_be_clickable((By.XPATH, click_xpath)))
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", el)
                        time.sleep(3)
                    except Exception as e:
                        print(f"  ✗ Click sulla riga fallito: {e}")
                        continue

                    # Attendi allegati
                    try:
                        wait.until(EC.presence_of_element_located((By.ID, ALLEGATI_PANEL_ID)))
                    except TimeoutException:
                        print(f"  ⚠ Panel allegati non trovato")
                        torna_alla_lista(driver, wait, BACK_TAB_ID)
                        continue

                    # CLICK sul primo PDF
                    # XPath: //*[@id="allegati_pnl"]/div/ul/li/a/div[2]/span
                    pdf_xpath = f"//*[@id='{ALLEGATI_PANEL_ID}']/div/ul/li/a/div[2]/span"
                    pdf_trovato = False
                    try:
                        pdf_link = wait.until(EC.element_to_be_clickable((By.XPATH, pdf_xpath)))
                        print(f"  📥 Scaricando PDF...")
                        pdf_link.click()
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
                    except TimeoutException:
                        print(f"  ⚠ PDF non trovato")
                    except Exception as e:
                        print(f"  ⚠ Errore scaricando PDF: {e}")

                    # Torna alla lista
                    torna_alla_lista(driver, wait, BACK_TAB_ID)

                except StaleElementReferenceException:
                    print(f"  ✗ Elemento stale")
                    torna_alla_lista(driver, wait, BACK_TAB_ID)
                except Exception as e:
                    print(f"  ✗ Errore: {e}")
                    torna_alla_lista(driver, wait, BACK_TAB_ID)

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


def torna_alla_lista(driver, wait, back_tab_id):
    """Torna alla lista cliccando il pulsante indietro"""
    try:
        # Click su SVG dentro il tab header per tornare
        svg_xpath = f"//*[@id='{back_tab_id}']/div/div/div/div[2]/svg"
        back_btn = wait.until(EC.element_to_be_clickable((By.XPATH, svg_xpath)))
        back_btn.click()
        time.sleep(2)
    except Exception as e:
        print(f"  ⚠ Errore tornando alla lista: {e}")
        time.sleep(1)
