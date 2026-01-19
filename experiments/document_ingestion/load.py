import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor


def run_load_test(minio_client, bucket, test_files, tracker, rate, duration):
    """Upload files at given rate, track E2E latency."""
    
    interval = 1.0 / rate if rate > 0 else 1.0
    file_idx = 0
    uploaded = 0
    start = time.time()
    
    def upload_file(path, obj_name):
        tracker.upload_started(obj_name)
        minio_client.fput_object(bucket, obj_name, str(path), content_type="application/pdf")
        tracker.upload_finished(obj_name)
    
    with ThreadPoolExecutor(max_workers=min(20, int(rate * 2) + 1)) as pool:
        while time.time() - start < duration:
            t0 = time.time()
            
            path = test_files[file_idx % len(test_files)]
            file_idx += 1
            
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            obj_name = f"exp/{ts}_{file_idx:05d}_{path.name}"
            
            pool.submit(upload_file, path, obj_name)
            uploaded += 1
            
            elapsed = time.time() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)
        
        pool.shutdown(wait=True)
    
    return uploaded


def wait_for_drain(qdrant_client, collection, timeout=120):
    """Wait until Qdrant point count stabilizes."""
    last_count = 0
    stable = 0
    start = time.time()
    
    while time.time() - start < timeout:
        try:
            info = qdrant_client.get_collection(collection)
            count = info.points_count or 0
            
            if count == last_count:
                stable += 1
                if stable >= 5:
                    return count
            else:
                stable = 0
            
            last_count = count
        except Exception:
            pass
        
        time.sleep(2)
    
    return last_count


def clear_test_data(minio_client, bucket, prefix="exp/"):
    """Remove previous test files from MinIO."""
    try:
        objects = list(minio_client.list_objects(bucket, prefix=prefix, recursive=True))
        for obj in objects:
            minio_client.remove_object(bucket, obj.object_name)
    except Exception:
        pass
