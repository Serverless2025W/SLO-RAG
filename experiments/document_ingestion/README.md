# Document Ingestion Scalability Experiment

Tests the document ingestion pipeline under varying load.

## Metrics

- **Ingestion Throughput**: Files fully indexed per second
- **E2E Latency**: Time from file upload to vector stored in Qdrant

## Usage

```bash
# with venv (recommended)
./run.sh --rates 1 2 5 10 --duration 60

# or directly
pip install -r requirements.txt
python experiment_runner.py --rates 1 2 5 10 15
```

## Output

Results saved to `./experiment_results/experiment_<timestamp>/`:
- `results.json` - raw data
- `report.md` - summary with figures
- `throughput.png` - throughput vs rate
- `latency.png` - E2E latency vs rate
- `combined.png` - both metrics
