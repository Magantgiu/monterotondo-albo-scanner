#!/usr/bin/env python3
"""
DISCOVERY SCANNER SEQUENZIALE PURO
Basato sui parametri di ieri sera: PARAM 50416 + KEY 56609
Segue la logica sequenziale: PARAM crescenti + KEY consecutivi per ogni PARAM
"""

import asyncio
import aiohttp
import time
import json
import argparse
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import logging
import sys

class SequentialDiscoveryScanner:
    """Discovery scanner che segue la logica sequenziale pura"""
    
    def __init__(self, reference_param=50416, reference_key=56609, max_concurrent=10, timeout=3):
        self.base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo/portale/albopretorio/getfile.aspx"
        
        # Parametri di riferimento (ieri sera)
        self.reference_param = reference_param
        self.reference_key = reference_key
        
        # Configuration conservativa
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        
        # Range di discovery basati sul punto di riferimento
        self.param_discovery_range = 20  # ±20 PARAM dal riferimento
        self.key_discovery_range = 100   # ±100 KEY dal riferimento
        
        # Risultati
        self.discovered_mappings = {}  # param_id -> [key_ids]
        self.working_combinations = []
        self.total_tests = 0
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
        
    async def test_combination(self, session: aiohttp.ClientSession, param_id: int, key_id: int) -> bool:
        """Test singola combinazione PARAM/KEY"""
        try:
            url = f"{self.base_url}?SOURCE=DB&PARAM={param_id}&KEY={key_id}"
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            
            async with session.head(url, timeout=timeout) as response:
                self.total_tests += 1
                
                if response.status == 200:
                    # Combinazione valida!
                    size = response.headers.get('Content-Length', '0')
                    
                    combination = {
                        'param_id': param_id,
                        'key_id': key_id,
                        'url': url,
                        'size_mb': round(int(size) / (1024 * 1024), 2) if size.isdigit() else 0,
                        'content_type': response.headers.get('Content-Type', 'unknown'),
                        'discovered_at': datetime.now().isoformat()
                    }
                    
                    self.working_combinations.append(combination)
                    
                    # Aggiungi alla mappatura
                    if param_id not in self.discovered_mappings:
                        self.discovered_mappings[param_id] = []
                    self.discovered_mappings[param_id].append(key_id)
                    
                    return True
                    
                return False
                
        except Exception as e:
            return False
    
    async def discover_param_keys_sequential(self, session: aiohttp.ClientSession, param_id: int, start_key: int) -> List[int]:
        """
        Scopre tutti i KEY di un PARAM seguendo logica sequenziale
        Testa KEY consecutivi finché non trova gap troppo grande
        """
        found_keys = []
        current_key = start_key
        consecutive_failures = 0
        max_gap = 10  # Massimo gap prima di considerare PARAM finito
        
        self.logger.info(f"🔍 Scanning PARAM {param_id} starting from KEY {start_key}")
        
        # Testa range intorno al punto di partenza
        test_range = 50  # Testa ±50 KEY dal punto di partenza
        
        for offset in range(-test_range, test_range + 1):
            test_key = start_key + offset
            
            if test_key < 56500:  # Limite inferiore ragionevole
                continue
                
            if await self.test_combination(session, param_id, test_key):
                found_keys.append(test_key)
                consecutive_failures = 0
                self.logger.info(f"  ✅ KEY {test_key} → PARAM {param_id}")
            else:
                consecutive_failures += 1
                
                # Se troppe failures consecutive, potrebbe essere finito
                if consecutive_failures > max_gap and found_keys:
                    break
        
        if found_keys:
            self.logger.info(f"  📊 PARAM {param_id}: {len(found_keys)} KEY trovati")
        else:
            self.logger.info(f"  ❌ PARAM {param_id}: Nessun KEY trovato")
            
        return sorted(found_keys)
    
    async def verify_reference_point(self, session: aiohttp.ClientSession) -> bool:
        """Verifica che il punto di riferimento sia ancora valido"""
        self.logger.info(f"🧪 Verifying reference point: PARAM {self.reference_param} + KEY {self.reference_key}")
        
        if await self.test_combination(session, self.reference_param, self.reference_key):
            self.logger.info("✅ Reference point still valid!")
            return True
        else:
            self.logger.warning("⚠️ Reference point no longer valid, but continuing discovery...")
            return False
    
    async def sequential_discovery_scan(self):
        """
        Discovery sequenziale basato sul punto di riferimento
        Esplora PARAM intorno al riferimento con logica sequenziale
        """
        self.logger.info("🚀 SEQUENTIAL DISCOVERY SCANNER STARTED")
        self.logger.info(f"📍 Reference point: PARAM {self.reference_param} + KEY {self.reference_key}")
        self.logger.info(f"🔍 Discovery range: ±{self.param_discovery_range} PARAM, ±{self.key_discovery_range} KEY")
        
        start_time = time.time()
        
        try:
            # Setup connessione
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
                
                # FASE 1: Verifica punto di riferimento
                await self.verify_reference_point(session)
                
                # FASE 2: Discovery sequenziale PARAM per PARAM
                param_start = self.reference_param - self.param_discovery_range
                param_end = self.reference_param + self.param_discovery_range
                
                self.logger.info(f"📊 Testing PARAM range: {param_start} → {param_end}")
                
                for param_id in range(param_start, param_end + 1):
                    # Per ogni PARAM, stima il KEY di partenza basandosi sul riferimento
                    param_offset = param_id - self.reference_param
                    
                    # Stima KEY basandosi sulla posizione del PARAM
                    # Assumiamo che PARAM successivi abbiano KEY più alti
                    estimated_key = self.reference_key + (param_offset * 2)  # Stima conservativa
                    
                    # Scopri i KEY per questo PARAM
                    param_keys = await self.discover_param_keys_sequential(session, param_id, estimated_key)
                    
                    if param_keys:
                        self.logger.info(f"✅ PARAM {param_id}: {len(param_keys)} KEY → {min(param_keys)}-{max(param_keys)}")
                    
                    # Pausa micro tra PARAM
                    await asyncio.sleep(0.1)
        
        except Exception as e:
            self.logger.error(f"Critical error in discovery: {e}")
            raise
        
        # FASE 3: Analisi risultati
        total_time = time.time() - start_time
        
        self.logger.info("🏁 SEQUENTIAL DISCOVERY COMPLETED")
        self.logger.info(f"⏱️ Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
        self.logger.info(f"🧪 Total tests: {self.total_tests}")
        self.logger.info(f"📊 Working combinations: {len(self.working_combinations)}")
        self.logger.info(f"📊 Active PARAMs: {len(self.discovered_mappings)}")
        
        if self.discovered_mappings:
            self.logger.info("📋 DISCOVERED ACTIVE PARAMs:")
            for param_id in sorted(self.discovered_mappings.keys()):
                keys = sorted(self.discovered_mappings[param_id])
                key_range = f"{keys[0]}-{keys[-1]}" if len(keys) > 1 else str(keys[0])
                self.logger.info(f"   PARAM {param_id}: {len(keys)} docs, KEY range {key_range}")
        
        return self.working_combinations
    
    def analyze_sequential_patterns(self) -> Dict:
        """Analizza i pattern sequenziali scoperti"""
        if not self.discovered_mappings:
            return {}
        
        analysis = {
            'reference_point': {
                'param': self.reference_param,
                'key': self.reference_key
            },
            'discovered_params': sorted(list(self.discovered_mappings.keys())),
            'param_count': len(self.discovered_mappings),
            'total_documents': len(self.working_combinations)
        }
        
        # Analisi range
        if self.discovered_mappings:
            min_param = min(self.discovered_mappings.keys())
            max_param = max(self.discovered_mappings.keys())
            analysis['param_range'] = {
                'min': min_param,
                'max': max_param,
                'span': max_param - min_param + 1
            }
            
            # Analisi KEY
            all_keys = []
            for keys in self.discovered_mappings.values():
                all_keys.extend(keys)
            
            if all_keys:
                analysis['key_range'] = {
                    'min': min(all_keys),
                    'max': max(all_keys),
                    'span': max(all_keys) - min(all_keys) + 1
                }
        
        # Pattern sequenziali
        sequential_patterns = []
        sorted_params = sorted(self.discovered_mappings.keys())
        
        for i in range(len(sorted_params) - 1):
            curr_param = sorted_params[i]
            next_param = sorted_params[i + 1]
            
            curr_keys = sorted(self.discovered_mappings[curr_param])
            next_keys = sorted(self.discovered_mappings[next_param])
            
            # Verifica se i KEY sono sequenziali
            if curr_keys and next_keys:
                last_key_curr = max(curr_keys)
                first_key_next = min(next_keys)
                gap = first_key_next - last_key_curr
                
                sequential_patterns.append({
                    'param_from': curr_param,
                    'param_to': next_param,
                    'last_key_from': last_key_curr,
                    'first_key_to': first_key_next,
                    'gap': gap,
                    'is_sequential': gap <= 5  # Gap piccolo = sequenziale
                })
        
        analysis['sequential_patterns'] = sequential_patterns
        
        return analysis
    
    def export_discovery_results(self):
        """Export risultati con focus sui pattern sequenziali"""
        timestamp = datetime.now()
        
        analysis = self.analyze_sequential_patterns()
        
        export_data = {
            'discovery_metadata': {
                'method': 'sequential_discovery_pure',
                'timestamp': timestamp.isoformat(),
                'reference_point': {
                    'param': self.reference_param,
                    'key': self.reference_key
                },
                'discovery_ranges': {
                    'param_range': self.param_discovery_range,
                    'key_range': self.key_discovery_range
                },
                'total_tests': self.total_tests
            },
            'pattern_analysis': analysis,
            'param_key_mappings': {
                str(param_id): sorted(keys) 
                for param_id, keys in self.discovered_mappings.items()
            },
            'working_combinations': sorted(
                self.working_combinations, 
                key=lambda x: (x['param_id'], x['key_id'])
            )
        }
        
        filename = f"monterotondo_sequential_discovery_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Sequential discovery results exported to: {filename}")
        return filename

async def main():
    parser = argparse.ArgumentParser(description='Monterotondo Sequential Discovery Scanner')
    parser.add_argument('--reference-param', type=int, default=50416, help='Reference PARAM from yesterday')
    parser.add_argument('--reference-key', type=int, default=56609, help='Reference KEY from yesterday')
    parser.add_argument('--param-range', type=int, default=20, help='PARAM discovery range (±N)')
    parser.add_argument('--key-range', type=int, default=100, help='KEY discovery range (±N)')
    parser.add_argument('--concurrency', type=int, default=10, help='Max concurrent requests')
    parser.add_argument('--timeout', type=int, default=3, help='Request timeout in seconds')
    
    args = parser.parse_args()
    
    print("🔍 MONTEROTONDO SEQUENTIAL DISCOVERY SCANNER")
    print("=" * 50)
    print("🎯 Based on yesterday's parameters + sequential logic")
    print(f"📍 Reference: PARAM {args.reference_param} + KEY {args.reference_key}")
    print(f"🔍 Will test ±{args.param_range} PARAM, ±{args.key_range} KEY")
    print("💡 Follows pure sequential logic: PARAM→KEY consecutive mapping")
    print()
    
    scanner = SequentialDiscoveryScanner(
        reference_param=args.reference_param,
        reference_key=args.reference_key,
        max_concurrent=args.concurrency,
        timeout=args.timeout
    )
    
    # Update discovery ranges if specified
    scanner.param_discovery_range = args.param_range
    scanner.key_discovery_range = args.key_range
    
    try:
        results = await scanner.sequential_discovery_scan()
        
        if results:
            filename = scanner.export_discovery_results()
            print(f"\n🎉 SEQUENTIAL DISCOVERY SUCCESS!")
            print(f"📊 Found {len(results)} working combinations")
            print(f"📊 Active PARAMs: {sorted(list(scanner.discovered_mappings.keys()))}")
            print(f"📄 Results saved to: {filename}")
            print(f"\n💡 These are the current active PARAM→KEY mappings!")
            print("🔄 Use these to update the main scanner with correct sequential logic")
        else:
            print("\n❌ No active combinations found")
            print("💡 Try adjusting the reference point or expanding the discovery ranges")
            
    except KeyboardInterrupt:
        print("\n⚠️ Discovery interrupted by user")
    except Exception as e:
        print(f"\n❌ Discovery failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
