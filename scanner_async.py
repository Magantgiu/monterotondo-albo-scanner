#!/usr/bin/env python3
"""
SISTEMA DI MONITORAGGIO ALBO PRETORIO MONTEROTONDO
Obiettivo: Monitoraggio continuo + generazione automatica articoli per cittadinanza
Basato sui 4 punti di riferimento forniti dall'utente
"""

import asyncio
import aiohttp
import time
import json
import argparse
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import logging
import sys
import os

class AlboPretorioMonitor:
    """Sistema di monitoraggio continuo dell'Albo Pretorio"""
    
    def __init__(self):
        self.base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo/portale/albopretorio/getfile.aspx"
        
        # Punti di riferimento forniti dall'utente
        self.reference_points = [
            (50416, 56609),
            (50435, 56694),
            (50436, 56697),
            (50437, 56698)
        ]
        
        # Configurazione monitoraggio
        self.max_concurrent = 10
        self.timeout = 5
        
        # Database locale per tracking
        self.known_documents = {}  # param_key -> document_info
        self.new_documents = []    # Documenti nuovi da ultimo scan
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('albo_monitor.log')
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def load_known_documents(self, filename='known_documents.json'):
        """Carica database documenti già noti"""
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.known_documents = data.get('documents', {})
                self.logger.info(f"Loaded {len(self.known_documents)} known documents from {filename}")
            except Exception as e:
                self.logger.error(f"Error loading known documents: {e}")
        else:
            self.logger.info("No previous database found, starting fresh")
    
    def save_known_documents(self, filename='known_documents.json'):
        """Salva database documenti aggiornato"""
        try:
            data = {
                'last_update': datetime.now().isoformat(),
                'total_documents': len(self.known_documents),
                'documents': self.known_documents
            }
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Saved {len(self.known_documents)} documents to {filename}")
        except Exception as e:
            self.logger.error(f"Error saving documents database: {e}")
    
    def calculate_scan_range(self) -> tuple:
        """Calcola range di scansione basato sui punti di riferimento"""
        params = [p for p, k in self.reference_points]
        keys = [k for p, k in self.reference_points]
        
        # Range conservativo: dal minimo noto fino a +20 PARAM/+50 KEY
        param_min = min(params)
        param_max = max(params) + 20
        key_min = min(keys) - 10  # Piccolo buffer verso il basso
        key_max = max(keys) + 50
        
        self.logger.info(f"Calculated scan range: PARAM {param_min}->{param_max}, KEY {key_min}->{key_max}")
        return param_min, param_max, key_min, key_max
    
    async def test_document_exists(self, session: aiohttp.ClientSession, param_id: int, key_id: int) -> Optional[Dict]:
        """Testa se un documento esiste e ne ottiene i metadati"""
        try:
            url = f"{self.base_url}?SOURCE=DB&PARAM={param_id}&KEY={key_id}"
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            async with session.head(url, timeout=timeout) as response:
                if response.status == 200:
                    size = response.headers.get('Content-Length', '0')
                    
                    return {
                        'param_id': param_id,
                        'key_id': key_id,
                        'url': url,
                        'size_mb': round(int(size) / (1024 * 1024), 2) if size.isdigit() else 0,
                        'content_type': response.headers.get('Content-Type', 'unknown'),
                        'last_modified': response.headers.get('Last-Modified', ''),
                        'discovered_at': datetime.now().isoformat(),
                        'status': 'active'
                    }
                else:
                    return None
        except Exception:
            return None
    
    async def scan_for_new_documents(self):
        """Scansiona per nuovi documenti pubblicati"""
        self.logger.info("Starting scan for new documents...")
        
        param_min, param_max, key_min, key_max = self.calculate_scan_range()
        self.new_documents = []
        
        total_tests = 0
        found_count = 0
        
        try:
            connector = aiohttp.TCPConnector(
                limit=self.max_concurrent,
                limit_per_host=self.max_concurrent,
                enable_cleanup_closed=True
            )
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                raise_for_status=False
            ) as session:
                
                # Strategia: scansiona PARAM dal più alto al più basso
                # (documenti più recenti hanno PARAM più alti)
                for param_id in range(param_max, param_min - 1, -1):
                    param_found_any = False
                    consecutive_failures = 0
                    
                    # Per ogni PARAM, scansiona KEY dal più alto
                    for key_id in range(key_max, key_min - 1, -1):
                        total_tests += 1
                        
                        # Controlla se già conosciamo questo documento
                        doc_key = f"{param_id}_{key_id}"
                        if doc_key in self.known_documents:
                            continue
                        
                        doc_info = await self.test_document_exists(session, param_id, key_id)
                        
                        if doc_info:
                            found_count += 1
                            param_found_any = True
                            consecutive_failures = 0
                            
                            # Nuovo documento trovato!
                            self.known_documents[doc_key] = doc_info
                            self.new_documents.append(doc_info)
                            
                            self.logger.info(f"NEW: PARAM {param_id} + KEY {key_id} = {doc_info['size_mb']}MB")
                        else:
                            consecutive_failures += 1
                        
                        # Se non troviamo documenti per un po', questo PARAM probabilmente è finito
                        if consecutive_failures > 20:
                            break
                        
                        await asyncio.sleep(0.05)
                    
                    # Se questo PARAM non ha documenti, probabilmente siamo andati troppo in alto
                    if not param_found_any and param_id > max([p for p, k in self.reference_points]):
                        self.logger.info(f"No documents found for PARAM {param_id}, likely beyond current range")
                        continue
                    
                    # Progress ogni 5 PARAM
                    if (param_max - param_id + 1) % 5 == 0:
                        progress = (param_max - param_id + 1) / (param_max - param_min + 1) * 100
                        self.logger.info(f"Progress: {progress:.1f}% | PARAM {param_id} | New docs: {len(self.new_documents)} | Tests: {total_tests}")
        
        except Exception as e:
            self.logger.error(f"Error during scan: {e}")
        
        self.logger.info(f"Scan completed: {len(self.new_documents)} new documents found in {total_tests} tests")
        return self.new_documents
    
    def generate_citizen_report(self) -> str:
        """Genera report per cittadinanza sui nuovi documenti"""
        if not self.new_documents:
            return "Nessun nuovo documento pubblicato dall'ultimo controllo."
        
        report_lines = [
            f"📋 ALBO PRETORIO MONTEROTONDO - Aggiornamento {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"",
            f"🆕 {len(self.new_documents)} nuovi documenti pubblicati:",
            f""
        ]
        
        # Raggruppa per PARAM (atto amministrativo)
        by_param = {}
        for doc in self.new_documents:
            param_id = doc['param_id']
            if param_id not in by_param:
                by_param[param_id] = []
            by_param[param_id].append(doc)
        
        # Ordina per PARAM decrescente (più recenti prima)
        for param_id in sorted(by_param.keys(), reverse=True):
            docs = by_param[param_id]
            
            if len(docs) == 1:
                doc = docs[0]
                report_lines.append(f"📄 Atto n. {param_id}")
                report_lines.append(f"   💾 Documento: {doc['size_mb']} MB")
                report_lines.append(f"   🔗 Link: {doc['url']}")
            else:
                report_lines.append(f"📄 Atto n. {param_id} ({len(docs)} allegati)")
                for i, doc in enumerate(docs, 1):
                    report_lines.append(f"   📎 Allegato {i}: {doc['size_mb']} MB")
                report_lines.append(f"   🔗 Link base: {docs[0]['url'].split('&KEY=')[0]}")
            
            report_lines.append("")
        
        report_lines.extend([
            "ℹ️ I documenti sono consultabili direttamente dal sito del Comune.",
            "🔄 Prossimo controllo automatico tra 1 ora.",
            f"⏰ Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}"
        ])
        
        return "\n".join(report_lines)
    
    def export_monitoring_data(self):
        """Esporta dati completi del monitoraggio"""
        timestamp = datetime.now()
        
        # Statistiche
        params_active = list(set(doc['param_id'] for doc in self.known_documents.values()))
        total_size = sum(doc.get('size_mb', 0) for doc in self.known_documents.values())
        
        export_data = {
            'monitoring_metadata': {
                'system': 'albo_pretorio_monitor',
                'timestamp': timestamp.isoformat(),
                'reference_points': self.reference_points,
                'monitoring_stats': {
                    'total_documents_tracked': len(self.known_documents),
                    'new_documents_this_scan': len(self.new_documents),
                    'active_param_range': f"{min(params_active) if params_active else 'N/A'}-{max(params_active) if params_active else 'N/A'}",
                    'total_size_mb': round(total_size, 2)
                }
            },
            'new_documents_report': self.generate_citizen_report(),
            'new_documents': self.new_documents,
            'all_known_documents': list(self.known_documents.values())
        }
        
        filename = f"albo_monitoring_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        # Genera anche report testuale per cittadinanza
        report_filename = f"report_cittadini_{timestamp.strftime('%Y%m%d_%H%M')}.txt"
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(self.generate_citizen_report())
        
        self.logger.info(f"Monitoring data exported to {filename}")
        self.logger.info(f"Citizen report exported to {report_filename}")
        
        return filename, report_filename
    
    async def run_monitoring_cycle(self):
        """Esegue un ciclo completo di monitoraggio"""
        self.logger.info("🚀 ALBO PRETORIO MONITORING CYCLE STARTED")
        
        # Carica documenti già noti
        self.load_known_documents()
        
        # Scansiona per nuovi documenti
        new_docs = await self.scan_for_new_documents()
        
        # Salva database aggiornato
        self.save_known_documents()
        
        # Esporta risultati
        data_file, report_file = self.export_monitoring_data()
        
        # Riassunto finale
        self.logger.info("🏁 MONITORING CYCLE COMPLETED")
        self.logger.info(f"📊 New documents found: {len(new_docs)}")
        self.logger.info(f"📊 Total documents tracked: {len(self.known_documents)}")
        
        if new_docs:
            self.logger.info("📢 CITIZEN ALERT: New documents available!")
            self.logger.info(f"📄 Report for citizens: {report_file}")
        else:
            self.logger.info("ℹ️ No new documents since last check")
        
        return new_docs

async def main():
    parser = argparse.ArgumentParser(description='Monterotondo Albo Pretorio Monitoring System')
    parser.add_argument('--mode', choices=['single', 'continuous'], default='single', 
                       help='Run mode: single scan or continuous monitoring')
    parser.add_argument('--interval', type=int, default=3600, 
                       help='Monitoring interval in seconds (default: 1 hour)')
    
    args = parser.parse_args()
    
    print("🏛️ MONTEROTONDO ALBO PRETORIO MONITORING SYSTEM")
    print("=" * 55)
    print("🎯 Objective: Monitor municipal notices for citizen information")
    print("📊 Reference points: 4 known PARAM/KEY combinations")
    print("📢 Output: Automated citizen reports on new publications")
    print()
    
    monitor = AlboPretorioMonitor()
    
    try:
        if args.mode == 'single':
            print("🔄 Running single monitoring cycle...")
            results = await monitor.run_monitoring_cycle()
            
            if results:
                print(f"\n📢 SUCCESS! Found {len(results)} new documents")
                print("📄 Check the generated report files for citizen communication")
            else:
                print("\n✅ No new documents found - system is up to date")
                
        elif args.mode == 'continuous':
            print(f"🔄 Starting continuous monitoring (interval: {args.interval}s)")
            
            cycle_count = 0
            while True:
                cycle_count += 1
                print(f"\n🔄 Monitoring cycle #{cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                try:
                    results = await monitor.run_monitoring_cycle()
                    
                    if results:
                        print(f"📢 ALERT: {len(results)} new documents published!")
                    else:
                        print("ℹ️ No new documents")
                        
                except Exception as e:
                    print(f"❌ Error in monitoring cycle: {e}")
                
                print(f"😴 Sleeping for {args.interval}s until next check...")
                await asyncio.sleep(args.interval)
                
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
    except Exception as e:
        print(f"\n💥 Monitoring failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
