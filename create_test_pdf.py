#!/usr/bin/env python3
"""Create a simple 2-page PDF for testing."""

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    
    def create_pdf():
        c = canvas.Canvas('test_document.pdf', pagesize=letter)
        
        # Page 1
        c.drawString(100, 750, 'Page 1 - Test Document')
        c.drawString(100, 700, 'This is the first page of our test document.')
        c.drawString(100, 650, 'It contains sample text for testing the text extraction workflow.')
        c.drawString(100, 600, 'The redpanda-connector will process chunks from this document.')
        c.drawString(100, 550, 'Integration tests will verify that messages are properly routed.')
        c.drawString(100, 500, 'This page contains enough text to be split into multiple chunks.')
        c.showPage()
        
        # Page 2
        c.drawString(100, 750, 'Page 2 - Test Document')
        c.drawString(100, 700, 'This is the second page of our test document.')
        c.drawString(100, 650, 'It contains additional sample text for testing purposes.')
        c.drawString(100, 600, 'The integration tests will verify end-to-end processing.')
        c.drawString(100, 550, 'Redis state management will be tested with conversation events.')
        c.drawString(100, 500, 'Summarization triggers will be verified when thresholds are exceeded.')
        c.save()
        print('PDF created successfully: test_document.pdf')
        
except ImportError:
    # Fallback: Use PyPDF2 or create a minimal PDF
    try:
        from PyPDF2 import PdfWriter, PdfReader
        import io
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.pagesizes import letter
        
        # Create PDF using reportlab (should work if installed)
        buffer = io.BytesIO()
        c = pdf_canvas.Canvas(buffer, pagesize=letter)
        
        # Page 1
        c.drawString(100, 750, 'Page 1 - Test Document')
        c.drawString(100, 700, 'This is the first page of our test document.')
        c.drawString(100, 650, 'It contains sample text for testing the text extraction workflow.')
        c.drawString(100, 600, 'The redpanda-connector will process chunks from this document.')
        c.showPage()
        
        # Page 2
        c.drawString(100, 750, 'Page 2 - Test Document')
        c.drawString(100, 700, 'This is the second page of our test document.')
        c.drawString(100, 650, 'It contains additional sample text for testing purposes.')
        c.drawString(100, 600, 'The integration tests will verify end-to-end processing.')
        c.save()
        
        # Write to file
        with open('test_document.pdf', 'wb') as f:
            f.write(buffer.getvalue())
        print('PDF created successfully: test_document.pdf')
        
    except ImportError:
        print("ERROR: Neither reportlab nor PyPDF2 with reportlab available.")
        print("Please install: pip install reportlab")
        print("Or create PDF manually with content:")
        print("  Page 1: 'Page 1 - Test Document' and sample text")
        print("  Page 2: 'Page 2 - Test Document' and sample text")

if __name__ == '__main__':
    create_pdf()
