import time
import threading
from qdrant_client import QdrantClient
from qdrant_client.http import models


class IngestionTracker:
    """Tracks files from upload to appearance in Qdrant."""
    
    def __init__(self, qdrant_host, qdrant_port, collection="documents"):
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port)
        self.collection = collection
        self.files = {}
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
    
    def upload_started(self, filename):
        with self.lock:
            self.files[filename] = {
                "upload_start": time.time(),
                "upload_end": None,
                "indexed_time": None,
                "chunks": 0
            }
    
    def upload_finished(self, filename):
        with self.lock:
            if filename in self.files:
                self.files[filename]["upload_end"] = time.time()
    
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._poll_qdrant, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _poll_qdrant(self):
        """Check Qdrant for indexed files."""
        while self.running:
            with self.lock:
                pending = [f for f, d in self.files.items() 
                          if d["upload_end"] and not d["indexed_time"]]
            
            now = time.time()
            for filename in pending:
                try:
                    results, _ = self.client.scroll(
                        collection_name=self.collection,
                        scroll_filter=models.Filter(must=[
                            models.FieldCondition(
                                key="filename",
                                match=models.MatchValue(value=filename)
                            )
                        ]),
                        limit=100,
                        with_payload=False,
                        with_vectors=False
                    )
                    
                    if results:
                        with self.lock:
                            self.files[filename]["indexed_time"] = now
                            self.files[filename]["chunks"] = len(results)
                except Exception:
                    pass
            
            time.sleep(0.5)
    
    def get_results(self):
        """Calculate metrics from tracked files."""
        with self.lock:
            data = dict(self.files)
        
        indexed = [f for f, d in data.items() if d["indexed_time"]]
        
        if not indexed:
            return {
                "files_uploaded": len(data),
                "files_indexed": 0,
                "ingestion_throughput": 0,
                "avg_e2e_latency": 0,
                "p50_e2e_latency": 0,
                "p95_e2e_latency": 0,
                "p99_e2e_latency": 0,
                "total_chunks": 0
            }
        
        latencies = []
        for f in indexed:
            d = data[f]
            latencies.append(d["indexed_time"] - d["upload_start"])
        
        latencies.sort()
        n = len(latencies)
        
        all_times = [(data[f]["upload_start"], data[f]["indexed_time"]) 
                     for f in indexed]
        start = min(t[0] for t in all_times)
        end = max(t[1] for t in all_times)
        duration = end - start
        
        total_chunks = sum(data[f]["chunks"] for f in indexed)
        
        return {
            "files_uploaded": len(data),
            "files_indexed": len(indexed),
            "ingestion_throughput": len(indexed) / duration if duration > 0 else 0,
            "avg_e2e_latency": sum(latencies) / n,
            "p50_e2e_latency": latencies[n // 2],
            "p95_e2e_latency": latencies[int(n * 0.95)] if n > 1 else latencies[-1],
            "p99_e2e_latency": latencies[int(n * 0.99)] if n > 1 else latencies[-1],
            "total_chunks": total_chunks
        }
