import io
import os
import re
import csv
import json
import base64
import requests
import pdfplumber
import pandas as pd
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt


def index(request):
    return render(request, 'converter/index.html')


def clean_cell(cell):
    if cell is None:
        return ''
    text = str(cell).strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def extract_tables_smarter(page):
    tables = page.extract_tables()
    if tables:
        return tables
    
    lines = page.lines
    if lines:
        table = page.extract_text()
        if table:
            return [[table]]
    return []


def extract_text_with_ocr(pdf_bytes):
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        images = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")
            images.append(base64.b64encode(img_data).decode('utf-8'))
        doc.close()
        
        if not images:
            return ''
        
        prompt = """Look at this image from a PDF document. Extract ALL text you can see, especially any handwritten text. 
Return the result as a JSON array of arrays with headers and rows, like: [["Header1", "Header2"], ["Row1Col1", "Row1Col2"], ["Row2Col1", "Row2Col2"]]
If it's not a table, just return a simple JSON array with one column: [["Line1"], ["Line2"], ["Line3"]]"""

        api_key = os.environ.get('GEMINI_API_KEY', '')
        if not api_key:
            api_url = 'https://api.ocr.space/parse/image'
            payload = {
                'isOverlayRequired': False,
                'detectOrientation': True,
                'language': 'eng',
                'isWriteable': True,
            }
            files = {'file': ('pdf.pdf', pdf_bytes, 'application/pdf')}
            headers = {'apikey': 'helloworld'}
            response = requests.post(api_url, files=files, data=payload, headers=headers, timeout=60)
            result = response.json()
            if result.get('ParsedResults'):
                texts = []
                for pr in result['ParsedResults']:
                    texts.append(pr.get('ParsedText', ''))
                return '\n'.join(texts)
            return ''
        
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}'
        
        headers = {'Content-Type': 'application/json'}
        
        parts = []
        for img_b64 in images:
            parts.append({"inline_data": {"mime_type": "image/png", "data": img_b64}})
        
        data = {
            "contents": [{"parts": parts + [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 8000,
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        result = response.json()
        
        if 'candidates' in result and result['candidates']:
            text = result['candidates'][0]['content']['parts'][0]['text']
            text = text.strip()
            if text.startswith('```json'):
                text = text[7:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()
            
            try:
                data = json.loads(text)
                if isinstance(data, list) and len(data) >= 1:
                    lines = []
                    for row in data:
                        if isinstance(row, list):
                            lines.append(' | '.join(str(cell) for cell in row))
                        else:
                            lines.append(str(row))
                    return '\n'.join(lines)
            except:
                return text
        
    except Exception as e:
        pass
    return ''


@csrf_exempt
def convert(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    pdf_file = request.FILES.get('pdf_file')
    output_format = request.POST.get('format', 'csv')

    if not pdf_file:
        return JsonResponse({'error': 'No PDF file uploaded.'}, status=400)

    if not pdf_file.name.lower().endswith('.pdf'):
        return JsonResponse({'error': 'Only PDF files are accepted.'}, status=400)

    try:
        pdf_bytes = pdf_file.read()
        all_tables = []
        raw_text_data = []
        
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)

            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                
                if tables and any(t for t in tables):
                    for table_idx, table in enumerate(tables):
                        if not table or not any(row for row in table):
                            continue
                            
                        cleaned = [[clean_cell(cell) for cell in row] for row in table]
                        
                        if not cleaned or not cleaned[0]:
                            continue
                            
                        first_row = cleaned[0]
                        has_header = any(cell for cell in first_row)
                        
                        if len(cleaned) > 1 and has_header:
                            header = cleaned[0]
                            data_rows = cleaned[1:]
                            
                            max_cols = max(len(row) for row in data_rows) if data_rows else len(header)
                            header = header + [''] * (max_cols - len(header))
                            
                            df = pd.DataFrame(data_rows, columns=header)
                        else:
                            df = pd.DataFrame(cleaned)
                        
                        all_tables.append(df)
                else:
                    text = page.extract_text()
                    if text:
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        for line in lines:
                            if line:
                                raw_text_data.append(line)
        
        if not all_tables:
            ocr_text = extract_text_with_ocr(pdf_bytes)
            if ocr_text:
                lines = [line.strip() for line in ocr_text.split('\n') if line.strip()]
                for line in lines:
                    if line:
                        raw_text_data.append(line)

        if all_tables:
            final_df = pd.concat(all_tables, ignore_index=True)
            final_df = final_df.fillna('')
        elif raw_text_data:
            final_df = pd.DataFrame({'Text': raw_text_data})
        else:
            return JsonResponse({'error': 'No extractable content found in the PDF.'}, status=400)

        base_name = os.path.splitext(pdf_file.name)[0]
        
        final_df.columns = [str(c) for c in final_df.columns]

        if output_format == 'excel':
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_df.to_excel(writer, index=False, sheet_name='Extracted Data')
                worksheet = writer.sheets['Extracted Data']
                
                for col_idx, col in enumerate(final_df.columns, 1):
                    max_len = max(
                        final_df[col].astype(str).map(len).max(),
                        len(str(col))
                    ) + 2
                    worksheet.column_dimensions[
                        worksheet.cell(row=1, column=col_idx).column_letter
                    ].width = min(max_len, 50)

            output.seek(0)
            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{base_name}.xlsx"'
            return response

        else:
            output = io.StringIO()
            final_df.to_csv(output, index=False)
            output.seek(0)
            response = HttpResponse(output.read(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{base_name}.csv"'
            return response

    except Exception as e:
        return JsonResponse({'error': f'Conversion failed: {str(e)}'}, status=500)
