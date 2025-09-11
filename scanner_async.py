#!/usr/bin/env python3
"""
SISTEMA MONITORAGGIO ALBO PRETORIO - COMPATIBILE CON WORKFLOW ESISTENTE
Accetta i parametri del workflow GitHub Actions esistente
Obiettivo: Monitoraggio + generazione report cittadini
"""

import asyncio
import aiohttp
import time
import json
import argparse
from datetime import datetime
from typing import Optional, Dict, List
import logging
import sys
import os

class CompatibleAlboMonitor:
    """Sistema di monitoraggio compatibile con workflow esistente"""
    
    def __init__(self, reference_param=50416, reference_key=56609, param_range=20, key_range=100, concurrency=10, timeout=5):
        self.base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo/portale/albopretorio/getfile.aspx"
        
        # Configurazione da parametri workflow
        self.reference_param = reference_param
        self.reference_key = reference_key
        self.param_range = param_range
        self.key_range = key_range
        self.max_concurrent = concurrency
        self.timeout = timeout
        
        # Punti di riferimento aggiornati (inclusi i 4 punti forniti)
        self.reference_points = [
            (50416, 56609),
            (50435, 56694),
            (50436, 56697),
            (50437, 56698)
        ]
        
        # Risultati
        self.results = []
        self.new_documents = []
        self.total_tests = 0
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
    
    def calculate_smart_range(self) -> tuple:
        """Calcola range intelligente basato su punti di riferimento e parametri"""
        # Usa i punti di riferimento per calcolare range ottimale
        ref_params = [p for p, k in self.reference_points]
        ref_keys = [k for p, k in self.reference_points]
        
        # Range dinamico basato sui riferimenti + parametri workflow
        param_min = max(self.reference_param - self.param_range, min(ref_params) - 5)
        param_max = max(ref_params) + self.param_range
        key_min = max(self.reference_key - self.key_range, min(ref_keys) - 10)
        key_max = max(ref_keys) + self.key_range
        
        self.logger.info(f"Smart range: PARAM {param_min}->{param_max}, KEY {key_min}->{key_max}")
        return param_min, param_max, key_min, key_max
    
    async def test_document(self, session: aiohttp.ClientSession, param_id: int, key_id: int) -> Optional[Dict]:
        """Testa documento e ritorna metadati se esiste"""
        try:
            url = f"{self.base_url}?SOURCE=DB&PARAM={param_id}&KEY={key_id}"
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            async with session.head(url, timeout=timeout) as response:
                self.total_tests += 1
                
                if response.status == 200:
                    size = response.headers.get('Content-Length', '0')
                    
                    return {
                        'param_id': param_id,
                        'key_id': key_id,
                        'url': url,
                        'size_mb': round(int(size) / (1024 * 1024), 2) if size.isdigit() else 0,
                        'content_type': response.headers.get('Content-Type', 'unknown'),
                        'discovered_at': datetime.now().isoformat(),
                        'status': 'active'
                    }
                else:
                    return None
        except Exception:
            return None
    
    async def smart_discovery_scan(self):
        """Scansione intelligente per discovery documenti"""
        self.logger.info("🚀 SMART ALBO DISCOVERY & MONITORING STARTED")
        self.logger.info(f"📍 Reference points: {len(self.reference_points)} known combinations")
        
        param_min, param_max, key_min, key_max = self.calculate_smart_range()
        
        start_time = time.time()
        
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
                
                # Verifica punti di riferimento
                self.logger.info("🧪 Verifying reference points...")
                active_refs = 0
                for param, key in self.reference_points:
                    doc = await self.test_document(session, param, key)
                    if doc:
                        self.results.append(doc)
                        active_refs += 1
                        self.logger.info(f"✅ REF: PARAM {param} + KEY {key}")
                    else:
                        self.logger.info(f"❌ REF: PARAM {param} + KEY {key}")
                
                self.logger.info(f"📊 Active reference points: {active_refs}/{len(self.reference_points)}")
                
                # Scansione espansa concentrata sui PARAM più alti (documenti recenti)
                semaphore = asyncio.Semaphore(self.max_concurrent)
                
                async def scan_param_efficient(param_id):
                    async with semaphore:
                        param_docs = []
                        consecutive_failures = 0
                        
                        # Concentrati sui KEY più alti (più recenti)
                        key_start = max(key_max - 30, key_min)  # Ultimi 30 KEY
                        
                        for key_id in range(key_max, key_start - 1, -1):
                            doc = await self.test_document(session, param_id, key_id)
                            
                            if doc:
                                param_docs.append(doc)
                                consecutive_failures = 0
                            else:
                                consecutive_failures += 1
                                
                                # Stop dopo molti fallimenti consecutivi
                                if consecutive_failures > 15:
                                    break
                        
                        return param_docs
                
                # Scansiona PARAM dal più alto al più basso (documenti più recenti prima)
                tasks = []
                for param_id in range(param_max, param_min - 1, -1):
                    tasks.append(scan_param_efficient(param_id))
                
                # Processa in batch per monitorare progresso
                batch_size = 10
                for i in range(0, len(tasks), batch_size):
                    batch_tasks = tasks[i:i + batch_size]
                    batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                    
                    for result in batch_results:
                        if isinstance(result, list):
                            self.results.extend(result)
                            if result:  # Nuovi documenti trovati
                                self.new_documents.extend(result)
                    
                    # Progress report
                    progress = min(100, (i + batch_size) / len(tasks) * 100)
                    elapsed = time.time() - start_time
                    
                    self.logger.info(
                        f"📈 Progress: {progress:5.1f}% | "
                        f"Docs found: {len(self.results)} | "
                        f"New docs: {len(self.new_documents)} | "
                        f"Tests: {self.total_tests} | "
                        f"Time: {elapsed:.1f}s"
                    )
                    
                    await asyncio.sleep(0.1)
        
        except Exception as e:
            self.logger.error(f"Error during scan: {e}")
        
        # Statistiche finali
        total_time = time.time() - start_time
        
        self.logger.info("🏁 DISCOVERY & MONITORING COMPLETED")
        self.logger.info(f"⏱️ Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
        self.logger.info(f"🧪 Total tests: {self.total_tests}")
        self.logger.info(f"📊 Total documents: {len(self.results)}")
        self.logger.info(f"🆕 New documents: {len(self.new_documents)}")
        
        if self.total_tests > 0:
            efficiency = len(self.results) / self.total_tests * 100
            self.logger.info(f"🎯 Efficiency: {efficiency:.1f}%")
        
        return self.results
    
    def generate_citizen_report(self) -> str:
        """Genera report per cittadinanza"""
        if not self.results:
            return "Nessun documento trovato nel sistema di monitoraggio."
        
        # Focus sui documenti nuovi se ce ne sono
        docs_to_report = self.new_documents if self.new_documents else self.results[-10:]  # Ultimi 10
        
        report_lines = [
            f"📋 ALBO PRETORIO MONTEROTONDO - Report {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"",
            f"📊 Documenti nel sistema: {len(self.results)}",
            f"🆕 Documenti evidenziati: {len(docs_to_report)}",
            f""
        ]
        
        # Raggruppa per PARAM
        by_param = {}
        for doc in docs_to_report:
            param_id = doc['param_id']
            if param_id not in by_param:
                by_param[param_id] = []
            by_param[param_id].append(doc)
        
        # Ordina per PARAM decrescente
        for param_id in sorted(by_param.keys(), reverse=True):
            docs = by_param[param_id]
            
            if len(docs) == 1:
                doc = docs[0]
                report_lines.append(f"📄 Atto n. {param_id}")
                report_lines.append(f"   💾 Dimensione: {doc['size_mb']} MB")
                report_lines.append(f"   🔗 Link: {doc['url']}")
            else:
                report_lines.append(f"📄 Atto n. {param_id} ({len(docs)} documenti)")
                total_size = sum(d['size_mb'] for d in docs)
                report_lines.append(f"   💾 Dimensione totale: {total_size:.1f} MB")
                report_lines.append(f"   🔗 Link base: {docs[0]['url'].split('&KEY=')[0]}")
            
            report_lines.append("")
        
        report_lines.extend([
            "ℹ️ Consultazione diretta: https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo/portale/albopretorio/",
            f"⏰ Report generato: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}"
        ])
        
        return "\n".join(report_lines)
    
    def export_results(self):
        """Export compatibile con workflow esistente"""
        timestamp = datetime.now()
        
        # Analisi per compatibilità
        if self.results:
            params_found = sorted(list(set(doc['param_id'] for doc in self.results)))
            keys_found = sorted([doc['key_id'] for doc in self.results])
            
            analysis = {
                'reference_points_verified': len([p for p in self.reference_points]),
                'param_range_discovered': f"{min(params_found)}-{max(params_found)}",
                'key_range_discovered': f"{min(keys_found)}-{max(keys_found)}",
                'total_documents': len(self.results),
                'new_documents': len(self.new_documents)
            }
        else:
            analysis = {'status': 'no_documents_found'}
        
        # Export principale (compatibile con workflow)
        export_data = {
            'scan_metadata': {
                'method': 'smart_albo_monitoring_discovery',
                'timestamp': timestamp.isoformat(),
                'configuration': {
                    'reference_param': self.reference_param,
                    'reference_key': self.reference_key,
                    'param_range': self.param_range,
                    'key_range': self.key_range,
                    'concurrency': self.max_concurrent
                },
                'total_tests': self.total_tests,
                'documents_found': len(self.results)
            },
            'analysis': analysis,
            'citizen_report': self.generate_citizen_report(),
            'documents': sorted(self.results, key=lambda x: (x['param_id'], x['key_id']), reverse=True)
        }
        
        # Nome file compatibile con workflow
        filename = f"monterotondo_sequential_discovery_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        # Report cittadini separato
        report_filename = f"report_cittadini_{timestamp.strftime('%Y%m%d_%H%M')}.txt"
        with open(report_filename, 'w', encoding='utf-8') as f:
            f.write(self.generate_citizen_report())
        
        self.logger.info(f"💾 Results exported to {filename}")
        self.logger.info(f"📢 Citizen report: {report_filename}")
        
        return filename

async def main():
    # Parser compatibile con workflow esistente
    parser = argparse.ArgumentParser(description='Monterotondo Smart Albo Monitoring')
    parser.add_argument('--reference-param', type=int, default=50416, help='Reference PARAM')
    parser.add_argument('--reference-key', type=int, default=56609, help='Reference KEY')
    parser.add_argument('--param-range', type=int, default=20, help='PARAM range')
    parser.add_argument('--key-range', type=int, default=100, help='KEY range')
    parser.add_argument('--concurrency', type=int, default=10, help='Concurrency')
    parser.add_argument('--timeout', type=int, default=5, help='Timeout')
    
    args = parser.parse_args()
    
    print("🏛️ MONTEROTONDO SMART ALBO MONITORING")
    print("=" * 45)
    print("🎯 Smart discovery + citizen reporting")
    print(f"📍 Reference: PARAM {args.reference_param} + KEY {args.reference_key}")
    print(f"🔍 Ranges: ±{args.param_range} PARAM, ±{args.key_range} KEY")
    print()
    
    monitor = CompatibleAlboMonitor(
        reference_param=args.reference_param,
        reference_key=args.reference_key,
        param_range=args.param_range,
        key_range=args.key_range,
        concurrency=args.concurrency,
        timeout=args.timeout
    )
    
    try:
        results = await monitor.smart_discovery_scan()
        
        if results:
            filename = monitor.export_results()
            print(f"\n🎉 SUCCESS! Found {len(results)} documents")
            print(f"📄 Data exported to: {filename}")
            print("📢 Citizen report generated for public communication")
        else:
            print("\n❌ No documents found in scan range")
            
    except Exception as e:
        print(f"\n💥 Monitoring failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
