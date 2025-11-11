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
from selenium.common.exceptions import TimeoutException

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

        # Chiudi cookie banner
        wait = WebDriverWait(driver, 8)
        for txt in ("Accetto", "ACCETTO", "Accetta"):
            try:
                btn = wait.until(EC.element_to_be_clickable((By.XPATH, f"//button[contains(text(), '{txt}')]")))
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1)
                break
            except TimeoutException:
                continue

        page = 1
        while page <= 3:  # max 3 pagine per run (evita loop infinito cloud)
            # Attendi tabella
            wait.until(EC.presence_of_element_located((By.ID, ALBO_TABLE_CONTAINER_ID)))
            time.sleep(2)

            # Estrai righe
            rows = driver.find_elements(By.CSS_SELECTOR, f"#{ALBO_TABLE_CONTAINER_ID} tbody tr")
            for idx, row in enumerate(rows):
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 5:
                    continue

                numero_atto = cells[3].text.strip()
                data_atto   = cells[7].text.strip()
                oggetto     = cells[4].text.strip()

                # Salta intestazioni o atti senza PDF
                if not numero_atto.isdigit() or "NOT.ART. 140 C.P.C." in oggetto:
                    continue

                # Converte data
                try:
                    data_pubb = dt.datetime.strptime(data_atto, "%d/%m/%Y").date()
                except ValueError:
                    continue
                if data_pubb < since:
                    continue

                # Entra nel dettaglio
                cells[4].click()
                time.sleep(3)
                wait.until(EC.presence_of_element_located((By.ID, ALLEGATI_PANEL_ID)))

                # Cerca primo PDF con “(Originale)”
                for link in driver.find_elements(By.XPATH, f"//*[@id='{ALLEGATI_PANEL_ID}']//a"):
                    txt = link.text
                    if "(Originale)" in txt and not txt.lower().endswith(".p7m"):
                        link.click()
                        time.sleep(3)  # attesa download
                        # Prendi file più recente dalla cartella
                        files = sorted(
                            [os.path.join(tmp_dir, f) for f in os.listdir(tmp_dir)],
                            key=os.path.getmtime,
                            reverse=True,
                        )
                        if files:
                            with open(files[0], "rb") as f:
                                pdf_bytes = f.read()
                            yield numero_atto, data_pubb, oggetto, pdf_bytes
                            # Rimuoviamo il file locale (cloud userà GCS)
                            os.remove(files[0])
                        break

                # Torna alla lista
                wait.until(EC.element_to_be_clickable((By.ID, LISTA_ATTI_BUTTON_ID))).click()
                time.sleep(2)

            # Prossima pagina
            try:
                next_btn = driver.find_element(By.LINK_TEXT, str(page + 1))
                next_btn.click()
                page += 1
                time.sleep(3)
            except Exception:
                break

    finally:
        driver.quit()
