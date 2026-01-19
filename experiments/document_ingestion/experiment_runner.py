import argparse
import json
import time
from pathlib import Path
from datetime import datetime

from minio import Minio
from qdrant_client import QdrantClient

from pdf_generator import generate_test_pdfs
from tracker import IngestionTracker
from load import run_load_test, wait_for_drain, clear_test_data
from report import generate_figures, write_report


def run_experiment(args):
    print("Document Ingestion Scalability Experiment")
    print("=" * 50)
    
    minio = Minio(
        args.minio_endpoint,
        access_key=args.minio_user,
        secret_key=args.minio_pass,
        secure=False
    )
    
    qdrant = QdrantClient(host=args.qdrant_host, port=args.qdrant_port)
    
    try:
        minio.list_buckets()
        print(f"✓ MinIO: {args.minio_endpoint}")
    except Exception as e:
        print(f"✗ MinIO connection failed: {e}")
        return
    
    try:
        qdrant.get_collections()
        print(f"✓ Qdrant: {args.qdrant_host}:{args.qdrant_port}")
    except Exception as e:
        print(f"✗ Qdrant connection failed: {e}")
        return
    
    test_files = generate_test_pdfs(args.test_dir, args.num_files)
    results = []
    
    for i, rate in enumerate(args.rates):
        print(f"\n[{i+1}/{len(args.rates)}] Rate: {rate} files/sec")
        print("-" * 40)
        
        pre_count = qdrant.get_collection("documents").points_count or 0
        clear_test_data(minio, args.bucket)
        time.sleep(1)
        
        tracker = IngestionTracker(args.qdrant_host, args.qdrant_port)
        tracker.start()
        
        uploaded = run_load_test(
            minio, args.bucket, test_files, tracker,
            rate=rate, duration=args.duration
        )
        print(f"  Uploaded: {uploaded} files")
        
        print("  Waiting for pipeline...")
        wait_for_drain(qdrant, "documents", timeout=120)
        
        time.sleep(3)
        tracker.stop()
        
        metrics = tracker.get_results()
        post_count = qdrant.get_collection("documents").points_count or 0
        chunks = post_count - pre_count
        
        result = {
            "rate": rate,
            "files_uploaded": uploaded,
            "files_indexed": metrics["files_indexed"],
            "ingestion_throughput": metrics["ingestion_throughput"],
            "avg_e2e_latency": metrics["avg_e2e_latency"],
            "p95_e2e_latency": metrics["p95_e2e_latency"],
            "chunks_stored": chunks
        }
        results.append(result)
        
        print(f"  Indexed: {metrics['files_indexed']} files")
        print(f"  Throughput: {metrics['ingestion_throughput']:.2f} files/sec")
        print(f"  Avg E2E: {metrics['avg_e2e_latency']:.2f}s")
        
        if i < len(args.rates) - 1:
            print(f"  Cooldown {args.cooldown}s...")
            time.sleep(args.cooldown)
    
    # save results
    out_dir = Path(args.output) / f"experiment_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    config = {
        "rates": args.rates,
        "duration": args.duration,
        "num_files": args.num_files
    }
    
    with open(out_dir / "results.json", "w") as f:
        json.dump({"results": results, "config": config}, f, indent=2)
    
    # print summary
    print("\n" + "=" * 90)
    print("RESULTS")
    print("=" * 90)
    print(f"{'Rate':<8} {'Throughput':<12} {'Uploaded':<10} {'Indexed':<10} {'Avg E2E':<10} {'P95 E2E':<10} {'Chunks':<8}")
    print("-" * 90)
    
    for r in results:
        print(f"{r['rate']:<8.1f} {r['ingestion_throughput']:<12.2f} {r['files_uploaded']:<10} "
              f"{r['files_indexed']:<10} {r['avg_e2e_latency']:<10.2f} {r['p95_e2e_latency']:<10.2f} "
              f"{r['chunks_stored']:<8}")
    
    print("=" * 90)
    print(f"\nResults saved to: {out_dir}")
    
    generate_figures(out_dir, results)
    write_report(out_dir / "report.md", results, config)


def main():
    parser = argparse.ArgumentParser(description="Document ingestion scalability test")
    
    parser.add_argument("--rates", nargs="+", type=float, default=[1, 2, 5, 10, 15])
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--cooldown", type=float, default=30)
    parser.add_argument("--num-files", type=int, default=50)
    
    parser.add_argument("--minio-endpoint", default="localhost:9000")
    parser.add_argument("--minio-user", default="admin")
    parser.add_argument("--minio-pass", default="password123")
    parser.add_argument("--bucket", default="documents")
    
    parser.add_argument("--qdrant-host", default="localhost")
    parser.add_argument("--qdrant-port", type=int, default=6333)
    
    parser.add_argument("--test-dir", default="./test_files")
    parser.add_argument("--output", default="./experiment_results")
    
    args = parser.parse_args()
    run_experiment(args)


if __name__ == "__main__":
    main()
