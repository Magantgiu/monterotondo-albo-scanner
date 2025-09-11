#!/usr/bin/env python3
"""
MONTEROTONDO ALBO PRETORIO - SCANNER ASINCRONO ULTRA-VELOCE
GitHub/VPS optimized version with massive parallelization
Target: 188 documents in 30-60 seconds
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

class MonterotondoAsyncScanner:
    """Ultra-fast async scanner for Monterotondo Albo Pretorio"""
    
    def __init__(self, key_start=56500, key_end=56688, max_concurrent=50, timeout=3):
        self.base_url = "https://servizionline.hspromilaprod.hypersicapp.net/cmsmonterotondo/portale/albopretorio/getfile.aspx"
        
        # Configuration
        self.key_start = key_start
        self.key_end = key_end
        self.max_concurrent = max_concurrent
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        
        # Known patterns from validation (KEY → PARAM mappings)
        self.known_mappings = {
            56640: 50421, 56641: 50422, 56644: 50428, 56645: 50428,
            56653: 50431, 56661: 50430, 56662: 50429, 56680: 50433,
            56681: 50433, 56682: 50433
        }
        
        # Results and metrics
        self.results = []
        self.total_requests = 0
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler('monterotondo_scan.log')
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def predict_params_for_key(self, key_id: int) -> List[int]:
        """Smart PARAM prediction based on discovered patterns"""
        if key_id in self.known_mappings:
            return [self.known_mappings[key_id]]
        
        candidates = []
        known_keys = sorted(self.known_mappings.keys())
        
        if len(known_keys) >= 2:
            # Find nearest known points for interpolation/extrapolation
            lower_key = max([k for k in known_keys if k <= key_id], default=None)
            upper_key = min([k for k in known_keys if k > key_id], default=None)
            
            if lower_key and upper_key:
                # Linear interpolation
                lower_param = self.known_mappings[lower_key]
                upper_param = self.known_mappings[upper_key]
                ratio = (key_id - lower_key) / (upper_key - lower_key)
                estimated = lower_param + (upper_param - lower_param) * ratio
                
                # Add candidates around estimate
                for offset in [-1, 0, 1]:
                    candidate = int(estimated) + offset
                    if 50400 <= candidate <= 50434:
                        candidates.append(candidate)
            
            elif lower_key:
                # Extrapolation upward
                if len(known_keys) >= 2:
                    trend_keys = known_keys[-2:]
                    key_diff = trend_keys[1] - trend_keys[0]
                    param_diff = self.known_mappings[trend_keys[1]] - self.known_mappings[trend_keys[0]]
                    
                    if key_diff > 0:
                        steps = (key_id - lower_key) / key_diff
                        estimated = self.known_mappings[lower_key] + param_diff * steps
                        
                        for offset in [-1, 0, 1]:
                            candidate = int(estimated) + offset
                            if 50400 <= candidate <= 50434:
                                candidates.append(candidate)
        
        # Fallback to most common PARAMs
        if not candidates:
            candidates = [50430, 50431, 50432, 50433, 50428, 50429]
        
        return candidates[:5]  # Max 5 candidates to keep it fast
    
    async def test_key_async(self, session: aiohttp.ClientSession, key_id: int) -> Optional[Dict]:
        """Async test of a KEY with smart PARAM prediction"""
        async with self.semaphore:
            param_candidates = self.predict_params_for_key(key_id)
            
            for param_id in param_candidates:
                try:
                    url = f"{self.base_url}?SOURCE=DB&PARAM={param_id}&KEY={key_id}"
                    
                    async with session.head(url, timeout=self.timeout) as response:
                        self.total_requests += 1
                        
                        if response.status == 200:
                            # Found! Get complete document info
                            doc_info = await self.get_document_info_async(session, param_id, key_id)
                            
                            # Update known mappings for future predictions
                            self.known_mappings[key_id] = param_id
                            
                            self.logger.info(f"✅ KEY {key_id} → PARAM {param_id}")
                            return doc_info
                
                except asyncio.TimeoutError:
                    self.logger.debug(f"⏰ Timeout KEY {key_id} PARAM {param_id}")
                    continue
                except Exception as e:
                    self.logger.debug(f"❌ Error KEY {key_id} PARAM {param_id}: {e}")
                    continue
            
            self.logger.debug(f"❌ KEY {key_id} → Not found")
            return None
    
    async def get_document_info_async(self, session: aiohttp.ClientSession, param_id: int, key_id: int) -> Dict:
        """Get complete document info asynchronously"""
        url = f"{self.base_url}?SOURCE=DB&PARAM={param_id}&KEY={key_id}"
        
        doc_info = {
            'param_id': param_id,
            'key_id': key_id,
            'url': url,
            'discovered_at': datetime.now().isoformat()
        }
        
        try:
            async with session.head(url, timeout=self.timeout) as response:
                if response.status == 200:
                    size = response.headers.get('Content-Length', '0')
                    doc_info.update({
                        'size_mb': round(int(size) / (1024 * 1024), 2),
                        'content_type': response.headers.get('Content-Type', ''),
                        'status': 'accessible'
                    })
        except:
            doc_info['status'] = 'error'
        
        return doc_info
    
    async def scan_ultra_fast(self):
        """Ultra-fast async scan with massive parallelization"""
        total_keys = self.key_end - self.key_start + 1
        
        self.logger.info("🚀 MONTEROTONDO ASYNC SCANNER STARTED")
        self.logger.info(f"📊 Range: KEY {self.key_start} → {self.key_end} ({total_keys} keys)")
        self.logger.info(f"⚡ Max concurrent: {self.max_concurrent}")
        self.logger.info(f"⏱️ Timeout: {self.timeout.total}s")
        
        start_time = time.time()
        
        # Optimized connection setup
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent * 2,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
            force_close=True,
            limit_per_host=self.max_concurrent
        )
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive'
        }
        
        async with aiohttp.ClientSession(
            connector=connector,
            headers=headers,
            timeout=self.timeout,
            raise_for_status=False
        ) as session:
            
            # Create all tasks
            all_keys = list(range(self.key_start, self.key_end + 1))
            tasks = [self.test_key_async(session, key_id) for key_id in all_keys]
            
            # Process in batches with progress reporting
            batch_size = 25
            completed = 0
            
            for i in range(0, len(tasks), batch_size):
                batch_tasks = tasks[i:i + batch_size]
                batch_start = time.time()
                
                # Wait for batch completion
                batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                # Process results
                for result in batch_results:
                    if isinstance(result, dict):
                        self.results.append(result)
                    elif isinstance(result, Exception):
                        self.logger.error(f"Task error: {result}")
                
                completed += len(batch_tasks)
                batch_time = time.time() - batch_start
                total_elapsed = time.time() - start_time
                progress = completed / len(all_keys) * 100
                
                self.logger.info(
                    f"📈 Progress: {progress:5.1f}% | "
                    f"Batch: {len(batch_tasks)} keys in {batch_time:.1f}s | "
                    f"Found: {len(self.results)} docs | "
                    f"Requests: {self.total_requests}"
                )
                
                # Small pause between batches
                await asyncio.sleep(0.1)
        
        # Final statistics
        total_time = time.time() - start_time
        
        self.logger.info("🏁 SCAN COMPLETED")
        self.logger.info(f"⏱️ Total time: {total_time:.1f}s ({total_time/60:.1f} min)")
        self.logger.info(f"📊 Documents found: {len(self.results)}/{total_keys} ({len(self.results)/total_keys*100:.1f}%)")
        self.logger.info(f"🧪 Total requests: {self.total_requests:,}")
        self.logger.info(f"⚡ Requests/second: {self.total_requests/total_time:.1f}")
        self.logger.info(f"📈 Documents/second: {len(self.results)/total_time:.1f}")
        
        if self.total_requests > 0:
            efficiency = len(self.results) / self.total_requests * 100
            self.logger.info(f"🎯 Efficiency: {efficiency:.1f}%")
        
        return self.results
    
    def export_results(self):
        """Export results with metadata"""
        if not self.results:
            self.logger.warning("No results to export")
            return None
        
        timestamp = datetime.now()
        
        export_data = {
            'scan_metadata': {
                'method': 'async_ultra_fast_github',
                'timestamp': timestamp.isoformat(),
                'configuration': {
                    'key_range': [self.key_start, self.key_end],
                    'max_concurrent': self.max_concurrent,
                    'timeout_seconds': self.timeout.total
                },
                'statistics': {
                    'total_requests': self.total_requests,
                    'documents_found': len(self.results),
                    'success_rate': len(self.results) / (self.key_end - self.key_start + 1) * 100
                }
            },
            'documents': sorted(self.results, key=lambda x: x['key_id'], reverse=True)
        }
        
        filename = f"monterotondo_scan_{timestamp.strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"💾 Results exported to: {filename}")
        return filename

async def main():
    parser = argparse.ArgumentParser(description='Monterotondo Albo Pretorio Ultra-Fast Scanner')
    parser.add_argument('--key-start', type=int, default=56500, help='Starting KEY')
    parser.add_argument('--key-end', type=int, default=56688, help='Ending KEY')
    parser.add_argument('--concurrency', type=int, default=50, help='Max concurrent requests')
    parser.add_argument('--timeout', type=int, default=3, help='Request timeout in seconds')
    
    args = parser.parse_args()
    
    print("🚀 MONTEROTONDO ALBO PRETORIO - ULTRA FAST SCANNER")
    print("=" * 55)
    print(f"📊 Configuration:")
    print(f"   KEY range: {args.key_start} → {args.key_end}")
    print(f"   Concurrency: {args.concurrency}")
    print(f"   Timeout: {args.timeout}s")
    print()
    
    scanner = MonterotondoAsyncScanner(
        key_start=args.key_start,
        key_end=args.key_end,
        max_concurrent=args.concurrency,
        timeout=args.timeout
    )
    
    try:
        results = await scanner.scan_ultra_fast()
        
        if results:
            filename = scanner.export_results()
            print(f"\n🎉 SUCCESS! Found {len(results)} documents")
            print(f"📄 Results saved to: {filename}")
        else:
            print("\n❌ No documents found")
            
    except KeyboardInterrupt:
        print("\n⚠️ Scan interrupted by user")
    except Exception as e:
        print(f"\n❌ Scan failed: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
