#!/usr/bin/env python3
"""
SCANNER TEST ULTRA-MINIMO
Test di base per verificare connettività e trovare almeno 1 documento
Timeout: massimo 5 minuti, poi si ferma
"""

import asyncio
import aiohttp
import time
import json
import argparse
from datetime import datetime
import logging
import sys

class MinimalTestScanner:
    """Scanner test minimo per debug connettività"""
    
    def __init__(self):
        self.base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo/portale/albopretorio/getfile.aspx"
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
        
        # Risultati
        self.results = []
        self.total_tests = 0
        self.start_time = None
        
        # Test points - combinazioni note che dovrebbero funzionare
        self.test_combinations = [
            # I tuoi dati di ieri sera
            (50416, 56609),
            
            # Variazioni intorno al punto noto
            (50416, 56608), (50416, 56610),
            (50415, 56609), (50417, 56609),
            
            # PARAM e KEY leggermente diversi
            (50416, 56605), (50416, 56615),
            (50410, 56609), (50420, 56609),
            
            # Range più ampio ma limitato
            (50400, 56600), (50430, 56620),
            (50405, 56605), (50425, 56625)
        ]
    
    def should_stop(self) -> bool:
        """Controlla se dovremmo fermarci (timeout sicurezza)"""
        if self.start_time:
            elapsed = time.time() - self.start_time
            if elapsed > 240:  # 4 minuti massimo
                self.logger.warning("⏰ Safety timeout reached (4 min), stopping scan")
                return True
        return False
    
    async def test_single_combination(self, session: aiohttp.ClientSession, param_id: int, key_id: int) -> bool:
        """Test singola combinazione con timeout breve"""
        if self.should_stop():
            return False
            
        try:
            url = f"{self.base_url}?SOURCE=DB&PARAM={param_id}&KEY={key_id}"
            self.total_tests += 1
            
            # Timeout molto breve per evitare blocchi
            timeout = aiohttp.ClientTimeout(total=3)
            
            self.logger.info(f"🧪 Testing PARAM {param_id} + KEY {key_id}")
            
            async with session.head(url, timeout=timeout) as response:
                if response.status == 200:
                    size = response.headers.get('Content-Length', '0')
                    
                    result = {
                        'param_id': param_id,
                        'key_id': key_id,
                        'url': url,
                        'size_mb': round(int(size) / (1024 * 1024), 2) if size.isdigit() else 0,
                        'content_type': response.headers.get('Content-Type', 'unknown'),
                        'status_code': response.status,
                        'discovered_at': datetime.now().isoformat()
                    }
                    
                    self.results.append(result)
                    self.logger.info(f"✅ SUCCESS: PARAM {param_id} + KEY {key_id} = {result['size_mb']}MB")
                    return True
                else:
                    self.logger.info(f"❌ FAIL: PARAM {param_id} + KEY {key_id} = HTTP {response.status}")
                    return False
                    
        except asyncio.TimeoutError:
            self.logger.info(f"⏰ TIMEOUT: PARAM {param_id} + KEY {key_id}")
            return False
        except Exception as e:
            self.logger.info(f"❌ ERROR: PARAM {param_id} + KEY {key_id} = {e}")
            return False
    
    async def run_minimal_test(self):
        """Test minimo per verificare connettività"""
        self.logger.info("🧪 MINIMAL TEST SCANNER STARTED")
        self.logger.info(f"🎯 Testing {len(self.test_combinations)} known combinations")
        self.logger.info("⏰ Max runtime: 4 minutes")
        self.logger.info("🔗 Testing connectivity to Monterotondo server...")
        
        self.start_time = time.time()
        
        try:
            # Connessione molto semplice
            timeout = aiohttp.ClientTimeout(total=5)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                # Test sequenziale (non parallelo) per evitare rate limiting
                for i, (param_id, key_id) in enumerate(self.test_combinations):
                    if self.should_stop():
                        break
                        
                    self.logger.info(f"📊 Test {i+1}/{len(self.test_combinations)}")
                    
                    success = await self.test_single_combination(session, param_id, key_id)
                    
                    if success:
                        self.logger.info(f"🎉 Found working combination! Continuing to test others...")
                    
                    # Pausa tra test per evitare rate limiting
                    await asyncio.sleep(1)
                    
                    # Se abbiamo trovato almeno 3 documenti, possiamo fermarci
                    if len(self.results) >= 3:
                        self.logger.info("✅ Found enough working combinations, stopping early")
                        break
        
        except Exception as e:
            self.logger.error(f"Critical error: {e}")
            
        # Risultati finali
        total_time = time.time() - self.start_time
        
        self.logger.info("🏁 MINIMAL TEST COMPLETED")
        self.logger.info(f"⏱️ Total time: {total_time:.1f}s")
        self.logger.info(f"🧪 Total tests: {self.total_tests}")
        self.logger.info(f"✅ Working combinations: {len(self.results)}")
        
        if self.results:
            self.logger.info("📊 WORKING COMBINATIONS FOUND:")
            for result in self.results:
                self.logger.info(f"   PARAM {result['param_id']} + KEY {result['key_id']} = {result['size_mb']}MB")
        else:
            self.logger.error("❌ NO working combinations found!")
            self.logger.error("🔍 Possible issues:")
            self.logger.error("   - Server is down or unreachable")
            self.logger.error("   - URL has changed")
            self.logger.error("   - All test combinations are invalid")
            self.logger.error("   - Network firewall blocking requests")
        
        return self.results
    
    def export_minimal_results(self):
        """Export risultati test minimo"""
        timestamp = datetime.now()
        
        export_data = {
            'test_metadata': {
                'method': 'minimal_connectivity_test',
                'timestamp': timestamp.isoformat(),
                'test_combinations_count': len(self.test_combinations),
                'total_tests_performed': self.total_tests,
                'working_combinations_found': len(self.results)
            },
            'test_combinations_tried': self.test_combinations,
            'working_combinations': self.results
        }
        
        filename = f"monterotondo_minimal_test_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Minimal test results exported to: {filename}")
        return filename

async def main():
    print("🧪 MONTEROTONDO MINIMAL TEST SCANNER")
    print("=" * 40)
    print("🎯 Goal: Test basic connectivity and find at least 1 working combination")
    print("⏰ Max runtime: 4 minutes")
    print("🔗 Tests known PARAM/KEY combinations sequentially")
    print()
    
    scanner = MinimalTestScanner()
    
    try:
        results = await scanner.run_minimal_test()
        
        if results:
            filename = scanner.export_minimal_results()
            print(f"\n🎉 SUCCESS! Found {len(results)} working combinations")
            print(f"📄 Results saved to: {filename}")
            print("\n💡 Next steps:")
            print("  1. Use these working combinations as reference points")
            print("  2. Expand search around successful PARAMs/KEYs")
            print("  3. The server is reachable and responding!")
        else:
            print(f"\n❌ NO working combinations found")
            print("🔍 This indicates a fundamental connectivity or parameter issue")
            
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
