import io
import os
import re
import csv
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
                        
                        df.insert(0, 'Page', page_num)
                        df.insert(1, 'Table_Number', table_idx + 1)
                        all_tables.append(df)
                else:
                    text = page.extract_text()
                    if text:
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        for line_idx, line in enumerate(lines):
                            if line:
                                raw_text_data.append({
                                    'Page': page_num,
                                    'Line': line_idx + 1,
                                    'Content': line,
                                    'Words': ' | '.join(line.split())
                                })

        if all_tables:
            final_df = pd.concat(all_tables, ignore_index=True)
            final_df = final_df.fillna('')
        elif raw_text_data:
            final_df = pd.DataFrame(raw_text_data)
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
