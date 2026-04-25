# PDF → CSV / Excel Converter (Django App)

A Django web app that converts any PDF file into CSV or Excel format.
It extracts tables automatically, and falls back to structured text rows when no tables are found.

---

## Project Structure

```
pdf_converter/
├── manage.py
├── requirements.txt
├── pdf_converter/          ← Django project package
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── converter/              ← App with conversion logic
    ├── __init__.py
    ├── urls.py
    ├── views.py
    └── templates/
        └── converter/
            └── index.html
```

---

## Step-by-Step Setup

### 1. Make sure Python is installed

You need Python 3.9 or higher.

```bash
python --version
# or
python3 --version
```

If not installed, download from https://python.org

---

### 2. Create a virtual environment

```bash
# Navigate to the project folder
cd pdf_converter

# Create virtual environment
python -m venv venv

# Activate it:
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

You'll see `(venv)` in your terminal — that means it's active.

---

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

This installs:
- **Django** — the web framework
- **pdfplumber** — PDF parsing and table extraction
- **pandas** — data manipulation
- **openpyxl** — Excel file creation
- **Pillow** — image support (used by pdfplumber)

---

### 4. Run the development server

No database setup is needed — this app doesn't use one.

```bash
python manage.py runserver
```

You should see:

```
Starting development server at http://127.0.0.1:8000/
```

---

### 5. Open the app

Go to your browser and visit:

```
http://127.0.0.1:8000/
```

---

## How to Use

1. **Upload a PDF** — drag and drop or click to browse
2. **Choose format** — CSV or Excel (.xlsx)
3. **Click "Convert PDF"** — the file downloads automatically

---

## How It Works

- Uses **pdfplumber** to scan every page of the PDF
- If a page has tables → extracts them as rows with `_page` and `_table` columns
- If a page has only text → splits lines into rows with a `text` column
- Converts the result to CSV (plain text) or Excel (styled, auto-sized columns)

---

## Troubleshooting

| Problem | Fix |
|--------|-----|
| `ModuleNotFoundError: No module named 'pdfplumber'` | Run `pip install -r requirements.txt` inside your venv |
| Port 8000 already in use | Run `python manage.py runserver 8080` and go to `http://127.0.0.1:8080` |
| Upload fails with large file | File limit is 20MB. Compress the PDF first |
| Empty output | PDF may be image-only (scanned). Add OCR support via pytesseract |

---

## Running on a Different Port

```bash
python manage.py runserver 8080
```

---

## Production Notes

Before deploying to production:
1. Change `SECRET_KEY` in `settings.py` to a long random string
2. Set `DEBUG = False`
3. Set `ALLOWED_HOSTS = ['yourdomain.com']`
4. Use gunicorn + nginx instead of Django's dev server
