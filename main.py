from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from docxtpl import DocxTemplate
import fitz  # PyMuPDF
import os
import re
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import HTMLResponse


app = FastAPI()

UPLOAD_DIR = "output"
TEMPLATE_PATH = "templates/excelencia_template.docx"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# CORS (optional, to allow n8n local/remote connections)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_text_from_pdf(path):
    text = ""
    doc = fitz.open(path)
    for page in doc:
        text += page.get_text()
    return text

def extract_name(text):
    lines = text.strip().split('\n')
    for line in lines:
        if len(line.split()) >= 2 and not any(w in line.lower() for w in ["resume", "cv"]):
            return line.strip()
    return "Candidate Name"

def rewrite_summary(text):
    sentences = re.split(r'[.!?]', text)
    summary = " ".join(sent.strip() for sent in sentences if len(sent.strip()) > 20)[:3]
    return f"Professionally summarized: {summary}..."

def extract_section(text, keywords):
    for keyword in keywords:
        pattern = rf"{keyword}[:\s\-]*([^\n]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return ""

@app.post("/format-resume")
async def format_resume(file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    extracted_text = extract_text_from_pdf(file_path)

    context = {
        "name": extract_name(extracted_text),
        "summary": rewrite_summary(extracted_text),
        "frameworks": extract_section(extracted_text, ["frameworks", "libraries", "technologies"]),
        "others": extract_section(extracted_text, ["others", "tools"]),
        "languages": extract_section(extracted_text, ["languages", "programming languages"]),
        "databases": extract_section(extracted_text, ["database", "databases"]),
        "tools": extract_section(extracted_text, ["tools", "utilities", "platforms"]),
        "internship": extract_section(extracted_text, ["internship", "training", "experience"]),
        "hobbies": extract_section(extracted_text, ["hobbies", "interests"]),
        "project_1_title": "Project Title 1",
        "project_1_description": "Description not extracted",
        "project_2_title": "Project Title 2",
        "project_2_description": "Description not extracted"
    }

    doc = DocxTemplate(TEMPLATE_PATH)
    doc.render(context)

    output_path = os.path.join(UPLOAD_DIR, "Formatted_Resume.docx")
    doc.save(output_path)

    return FileResponse(
        output_path,
        filename="Formatted_Resume.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@app.post("/upload-resume-proxy")
async def proxy_upload(file: UploadFile = File(...)):
    import requests
    from io import BytesIO

    files = {"data": (file.filename, await file.read(), file.content_type)}
    response = requests.post(
        "https://deekshana-ravikumar.app.n8n.cloud/webhook/upload-resume",
        files=files,
    )

    # Try returning JSON if available
    try:
        return JSONResponse(status_code=response.status_code, content=response.json())
    except ValueError:
        # If response is a file (not JSON), stream it
        return StreamingResponse(BytesIO(response.content), media_type="application/octet-stream")


from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <title>Resume Formatter Upload</title>
      <style>
        body { font-family: Arial; background: #f4f4f4; padding: 40px; text-align: center; }
        input[type="file"], button { margin-top: 20px; padding: 10px; }
        #result { margin-top: 30px; }
      </style>
    </head>
    <body>

      <h1>Upload Resume (PDF)</h1>
      <form id="uploadForm">
        <input type="file" name="file" id="fileInput" accept="application/pdf" required />
        <br>
        <button type="submit">Upload & Format</button>
      </form>

      <div id="result"></div>

      <script>
        const webhookUrl = "/upload-resume-proxy";

        document.getElementById("uploadForm").addEventListener("submit", async function(e) {
          e.preventDefault();

          const file = document.getElementById("fileInput").files[0];
          const resultDiv = document.getElementById("result");
          if (!file) return (resultDiv.innerText = "Please select a file.");

          const formData = new FormData();
          formData.append("file", file);
          resultDiv.innerHTML = "Uploading and formatting resume...";

          try {
            const res = await fetch(webhookUrl, {
              method: "POST",
              body: formData,
            });

            const contentType = res.headers.get("content-type") || "";
            if (!res.ok) throw new Error(`Server error: ${res.status}`);

            if (contentType.includes("application/json")) {
              const json = await res.json();
              resultDiv.innerHTML = `<p>${json.message}</p><a href="${json.driveLink}" target="_blank"><button>Open in Google Drive</button></a>`;
            } else {
              const blob = await res.blob();
              const downloadUrl = URL.createObjectURL(blob);
              resultDiv.innerHTML = `<a href="${downloadUrl}" download="Formatted_Resume.docx"><button>Download Resume</button></a>`;
            }

          } catch (err) {
            resultDiv.innerText = "❌ Error: " + err.message;
          }
        });
      </script>
    </body>
    </html>
    """
