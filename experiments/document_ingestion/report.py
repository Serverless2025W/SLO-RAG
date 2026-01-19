from datetime import datetime
import matplotlib
import matplotlib.pyplot as plt


def generate_figures(out_dir, results):
    """Generate charts from experiment results."""
    
    rates = [r["rate"] for r in results]
    throughputs = [r["ingestion_throughput"] for r in results]
    avg_latencies = [r["avg_e2e_latency"] for r in results]
    p95_latencies = [r["p95_e2e_latency"] for r in results]
    
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(rates, throughputs, 'o-', linewidth=2, markersize=8, color='#2563eb')
    ax.plot(rates, rates, '--', color='gray', alpha=0.5, label='Ideal (1:1)')
    ax.set_xlabel('Upload Rate (files/sec)', fontsize=11)
    ax.set_ylabel('Ingestion Throughput (files/sec)', fontsize=11)
    ax.set_title('Ingestion Throughput vs Upload Rate', fontsize=12, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, max(rates) * 1.1)
    ax.set_ylim(0, max(max(throughputs), max(rates)) * 1.1)
    fig.tight_layout()
    fig.savefig(out_dir / 'throughput.png', dpi=150)
    plt.close(fig)
    
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(rates, avg_latencies, 'o-', linewidth=2, markersize=8, color='#2563eb', label='Avg')
    ax.plot(rates, p95_latencies, 's--', linewidth=2, markersize=8, color='#dc2626', label='P95')
    ax.set_xlabel('Upload Rate (files/sec)', fontsize=11)
    ax.set_ylabel('E2E Latency (seconds)', fontsize=11)
    ax.set_title('End-to-End Latency vs Upload Rate', fontsize=12, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, max(rates) * 1.1)
    fig.tight_layout()
    fig.savefig(out_dir / 'latency.png', dpi=150)
    plt.close(fig)
    
    fig, ax1 = plt.subplots(figsize=(9, 5))
    ax2 = ax1.twinx()
    
    l1 = ax1.plot(rates, throughputs, 'o-', linewidth=2, markersize=8, color='#2563eb', label='Throughput')
    l2 = ax2.plot(rates, avg_latencies, 's-', linewidth=2, markersize=8, color='#dc2626', label='Avg Latency')
    
    ax1.set_xlabel('Upload Rate (files/sec)', fontsize=11)
    ax1.set_ylabel('Throughput (files/sec)', fontsize=11, color='#2563eb')
    ax2.set_ylabel('Latency (seconds)', fontsize=11, color='#dc2626')
    ax1.tick_params(axis='y', labelcolor='#2563eb')
    ax2.tick_params(axis='y', labelcolor='#dc2626')
    
    lines = l1 + l2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left')
    
    ax1.set_title('Throughput and Latency vs Upload Rate', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / 'combined.png', dpi=150)
    plt.close(fig)
    
    print(f"  Figures saved: throughput.png, latency.png, combined.png")


def write_report(path, results, config):
    """Write markdown report."""
    
    with open(path, "w") as f:
        f.write("# Document Ingestion Scalability Results\n\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        
        f.write("## Configuration\n\n")
        f.write(f"- Rates tested: {config['rates']}\n")
        f.write(f"- Duration per rate: {config['duration']}s\n")
        f.write(f"- Test files: {config['num_files']}\n\n")
        
        f.write("## Results\n\n")
        f.write("| Rate | Throughput | Uploaded | Indexed | Avg E2E | P95 E2E | Chunks |\n")
        f.write("|------|------------|----------|---------|---------|---------|--------|\n")
        
        for r in results:
            f.write(f"| {r['rate']:.1f} | {r['ingestion_throughput']:.2f} | "
                   f"{r['files_uploaded']} | {r['files_indexed']} | "
                   f"{r['avg_e2e_latency']:.2f}s | {r['p95_e2e_latency']:.2f}s | "
                   f"{r['chunks_stored']} |\n")
        
        f.write("\n## Figures\n\n")
        f.write("![Throughput](throughput.png)\n\n")
        f.write("![Latency](latency.png)\n\n")
        f.write("![Combined](combined.png)\n\n")
        
        f.write("## Metrics\n\n")
        f.write("- **Throughput**: Files fully indexed per second\n")
        f.write("- **E2E Latency**: Time from upload start to vector stored in Qdrant\n")
