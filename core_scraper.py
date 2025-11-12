"""
core_scraper.py
Scarica atti da albo Hypersic (Monterotondo) – solo cloud-ready.
Restituisce: (id, data, oggetto, pdf_bytes) per ogni atto.
SQLite/CSV rimossi: i dati vengono salvati da scraper_stateless.py su Supabase + GCS.
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ---------- CONFIG ----------
ALBO_TABLE_CONTAINER_ID = (
    "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_risultati_tab_risultati_table"
)
LISTA_ATTI_BUTTON_ID    = "tab_pnlnav_tab_risultati"
ALLEGATI_PANEL_ID       = (
    "ctl00_ctl00_area_main_ContentPlaceHolderContenuto_albo_pretorio_container_tab_dettaglio_tab_dettaglio_sidebar_allegati_tab_dettaglio_sidebar_allegati_pnl"
)
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

    # Download automatico PDF (cartella temporanea locale)
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
    try:
        base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo"
        albo_url = f"{base_url}/portale/albopretorio/albopretorioconsultazione.aspx?P=400"
        driver.get(os.getenv("ALBO_URL", albo_url))
        print(f"📄 Caricamento pagina: {os.getenv('ALBO_URL', albo_url)}")

        # Chiudi cookie banner
        wait = WebDriverWait(driver, 10)
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
        while page <= 3:  # max 3 pagine per run (evita loop infinito cloud)
            print(f"📖 Pagina {page}")
            
            # Attendi tabella - prova prima con l'ID esatto, poi con selettori alternativi
            try:
                wait.until(EC.presence_of_element_located((By.ID, ALBO_TABLE_CONTAINER_ID)))
                print(f"✓ Tabella trovata con ID: {ALBO_TABLE_CONTAINER_ID}")
            except TimeoutException:
                print(f"⚠ ID {ALBO_TABLE_CONTAINER_ID} non trovato, provo selettori alternativi...")
                # Prova selettori alternativi
                try:
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table.tabella_risultati")))
                    print("✓ Tabella trovata con classe: tabella_risultati")
                except TimeoutException:
                    try:
                        wait.until(EC.presence_of_element_located((By.XPATH, "//table[contains(@id, 'tab_risultati')]")))
                        print("✓ Tabella trovata con XPath")
                    except TimeoutException:
                        print("✗ Nessuna tabella trovata su questa pagina")
                        break
            
            time.sleep(2)

            # Estrai righe - prova selettori multipli
            rows = []
            try:
                rows = driver.find_elements(By.CSS_SELECTOR, f"#{ALBO_TABLE_CONTAINER_ID} tbody tr")
            except NoSuchElementException:
                pass
            
            if not rows:
                try:
                    rows = driver.find_elements(By.XPATH, "//table[contains(@id, 'tab_risultati')]//tbody//tr")
                except NoSuchElementException:
                    pass
            
            if not rows:
                print("✗ Nessuna riga trovata")
                break

            print(f"📊 Trovate {len(rows)} righe")

            for idx, row in enumerate(rows):
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 5:
                        continue

                    numero_atto = cells[3].text.strip()
                    data_atto   = cells[7].text.strip() if len(cells) > 7 else ""
                    oggetto     = cells[4].text.strip()

                    # Salta intestazioni o atti senza PDF
                    if not numero_atto.isdigit() or "NOT.ART. 140 C.P.C." in oggetto or not data_atto:
                        continue

                    # Converte data
                    try:
                        data_pubb = dt.datetime.strptime(data_atto, "%d/%m/%Y").date()
                    except ValueError:
                        print(f"⚠ Data non valida: {data_atto}")
                        continue
                    
                    if data_pubb < since:
                        print(f"⏭ Atto {numero_atto} più vecchio di {since}")
                        continue

                    print(f"🔍 Elaboro atto {numero_atto} ({data_pubb}): {oggetto[:50]}...")

                    # Entra nel dettaglio
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cells[4])
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", cells[4])
                    time.sleep(3)
                    
                    try:
                        wait.until(EC.presence_of_element_located((By.ID, ALLEGATI_PANEL_ID)))
                    except TimeoutException:
                        print(f"⚠ Panel allegati non trovato per atto {numero_atto}")
                        # Torna alla lista comunque
                        try:
                            wait.until(EC.element_to_be_clickable((By.ID, LISTA_ATTI_BUTTON_ID))).click()
                            time.sleep(2)
                        except:
                            pass
                        continue

                    # Cerca primo PDF con "(Originale)"
                    pdf_trovato = False
                    for link in driver.find_elements(By.XPATH, f"//*[@id='{ALLEGATI_PANEL_ID}']//a"):
                        txt = link.text
                        if "(Originale)" in txt and not txt.lower().endswith(".p7m"):
                            print(f"  📥 Scarico: {txt}")
                            link.click()
                            time.sleep(4)  # attesa download
                            
                            # Prendi file più recente dalla cartella
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
                                # Rimuoviamo il file locale (cloud userà GCS)
                                os.remove(files[0])
                                pdf_trovato = True
                            break
                    
                    if not pdf_trovato:
                        print(f"  ⚠ Nessun PDF originale trovato per {numero_atto}")

                    # Torna alla lista
                    try:
                        wait.until(EC.element_to_be_clickable((By.ID, LISTA_ATTI_BUTTON_ID))).click()
                        time.sleep(2)
                    except:
                        pass

                except Exception as e:
                    print(f"✗ Errore elaborando riga {idx}: {e}")
                    continue

            # Prossima pagina
            try:
                next_btn = driver.find_element(By.LINK_TEXT, str(page + 1))
                next_btn.click()
                page += 1
                time.sleep(3)
                print(f"→ Passando a pagina {page}")
            except Exception:
                print("→ Nessuna pagina successiva trovata")
                break

    except Exception as e:
        print(f"✗ Errore generale: {e}")
        raise
    finally:
        driver.quit()
        print("✓ Browser chiuso")
