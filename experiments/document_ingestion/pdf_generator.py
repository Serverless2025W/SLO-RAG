from io import BytesIO
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


SAMPLE_TEXT = [
    "Cloud computing has transformed how organizations deploy applications. "
    "Serverless architectures abstract away infrastructure management.",
    
    "Function-as-a-Service platforms enable event-driven computing at scale. "
    "They automatically scale based on incoming request volume.",
    
    "Document processing pipelines are common serverless use cases. "
    "The ability to process documents in parallel makes FaaS ideal for batch uploads.",
    
    "Vector databases enable semantic search capabilities. "
    "They store document embeddings for similarity matching.",
]


def make_pdf(num_pages=3):
    """Generate a test PDF in memory."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    
    for page in range(num_pages):
        c.setFont("Helvetica", 11)
        y = height - 72
        
        for para in SAMPLE_TEXT:
            words = para.split()
            line = ""
            for word in words:
                if c.stringWidth(line + " " + word) < width - 144:
                    line = line + " " + word if line else word
                else:
                    c.drawString(72, y, line)
                    y -= 14
                    line = word
            if line:
                c.drawString(72, y, line)
                y -= 28
        
        c.showPage()
    
    c.save()
    buf.seek(0)
    return buf


def generate_test_pdfs(output_dir, count=50):
    """Generate test PDF files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    existing = list(output_dir.glob("*.pdf"))
    if len(existing) >= count:
        print(f"Using {len(existing)} existing test files")
        return existing
    
    print(f"Generating {count} test PDFs...")
    files = []
    for i in range(count):
        path = output_dir / f"test_{i:04d}.pdf"
        pdf_data = make_pdf(num_pages=2)
        path.write_bytes(pdf_data.read())
        files.append(path)
    
    return files
