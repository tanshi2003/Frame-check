# FrameCheck

Free, browser-based video review for motion and graphic designers.

FrameCheck extracts timestamped frames from uploaded videos, runs OCR to surface visible text, and checks extracted text for spelling/grammar issues. The app is designed to run without paid AI APIs or user accounts.

## Stack
- FastAPI + Python
- FFmpeg for video metadata and frame extraction
- Tesseract OCR (local)
- Vanilla HTML/CSS/JavaScript frontend served by FastAPI

## Run locally

Requirements: Python 3.10+, FFmpeg, Tesseract OCR.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000.

Set `TESSERACT_CMD` if the Tesseract executable is not on PATH.

## Deploy
A Dockerfile is included. Deploy the repository as a Docker web service on a free container host where available. The service needs writable temporary storage and FFmpeg + Tesseract installed in the image.

## Privacy
Videos are processed on the server in temporary folders and deleted after the job. Do not upload confidential client media to a public instance unless you trust its operator. Public deployments should configure request size limits and rate limiting appropriate to their host.

## Limitations
OCR accuracy depends on resolution, contrast, animation speed, and font. Spell/grammar findings are suggestions, not a substitute for human proofreading. This MVP processes one video per request and caps duration/size to protect shared free resources.
