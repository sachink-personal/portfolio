import os
import csv
import sys

def extract_pdf_clean(pdf_path, txt_path):
    print(f"Attempting to extract {pdf_path} to {txt_path}...")
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for i, page in enumerate(reader.pages):
            text += f"--- Page {i+1} ---\n"
            text += page.extract_text() or ""
            text += "\n\n"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        print("Successfully extracted PDF via pypdf.")
        return True
    except ImportError:
        print("pypdf not found. Trying fitz (PyMuPDF)...")
    
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        text = ""
        for i, page in enumerate(doc):
            text += f"--- Page {i+1} ---\n"
            text += page.get_text()
            text += "\n\n"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        print("Successfully extracted PDF via fitz.")
        return True
    except ImportError:
        print("fitz not found. Trying pdfplumber...")
        
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text += f"--- Page {i+1} ---\n"
                text += page.extract_text() or ""
                text += "\n\n"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
        print("Successfully extracted PDF via pdfplumber.")
        return True
    except ImportError:
        print("pdfplumber not found.")
        
    # If no library found, write error.
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("No PDF extraction library available (tried pypdf, fitz, pdfplumber).")
    print("Failed to find a PDF library.")
    return False

def inspect_data_files():
    output = []
    
    # 1. Chartink CSV
    csv_file = 'downloads/for_Portfolio_7_13_2026.csv'
    if os.path.exists(csv_file):
        output.append("=== CHARTINK CSV FILE ===")
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                if rows:
                    output.append(f"Columns: {rows[0]}")
                    output.append(f"Number of rows: {len(rows)}")
                    output.append("First 2 data rows:")
                    for r in rows[1:3]:
                        output.append(str(r))
                else:
                    output.append("Empty CSV file")
        except Exception as e:
            output.append(f"Error reading CSV: {e}")
    else:
        output.append(f"CSV file not found: {csv_file}")
        
    # 2. Screener Excel
    screener_file = 'downloads/screener.xlsx'
    if os.path.exists(screener_file):
        output.append("\n=== SCREENER.IN EXCEL FILE ===")
        try:
            import openpyxl
            wb = openpyxl.load_workbook(screener_file, read_only=True)
            ws = wb.active
            rows = []
            for row in ws.iter_rows(max_row=5, values_only=True):
                rows.append(row)
            if rows:
                output.append(f"Columns: {list(rows[0])}")
                output.append("First 2 data rows:")
                for r in rows[1:3]:
                    output.append(str(list(r)))
            else:
                output.append("Empty Excel file")
        except Exception as e:
            output.append(f"Error reading Excel: {e}")
    else:
        output.append(f"Excel file not found: {screener_file}")

    with open("downloads/file_meta.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    print("Successfully wrote metadata to downloads/file_meta.txt")

if __name__ == "__main__":
    extract_pdf_clean("Quantitative Portfolio Management Engine Roadmap - Google Gemini.pdf", "downloads/pdf_roadmap.txt")
    inspect_data_files()
