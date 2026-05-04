# Quick Start Guide

Get up and running in 5 minutes.

## 1️⃣ Install (2 min)

```bash
cd job_hunt_tool
python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
pip install beautifulsoup4  # For Indeed scraper
playwright install chromium  # For LinkedIn scraper
```

## 2️⃣ Configure (2 min)

```bash
cp .env.template .env
```

Edit `.env`:
```
GEMINI_API_KEY=<get from https://aistudio.google.com>
LINKEDIN_EMAIL=<your email>
LINKEDIN_PASSWORD=<your password>
```

Edit `config.yaml`:
```yaml
search:
  roles:
    - "Product Manager"     # Change to your target roles
  locations:
    - "India"              # Change to your target locations
  salary_min_inr: 1500000

portals:
  - naukri
  - greenhouse
  - lever
  - indeed_india
```

## 3️⃣ Resume (30 sec)

Place your resume at:
- `resume/CV_Tarun_Gupta_1225_updated_No.pdf` (auto-detected)
- Or any name: `resume/my_resume.pdf` or `.docx` or `.txt`

## 4️⃣ Run (1 min)

```bash
streamlit run app.py
```

Visit: http://localhost:8501

## 5️⃣ Search (1 min)

1. Click **🔍 Search** tab
2. Review/edit search criteria
3. Click **🚀 Start Search**
4. Wait for completion (30 sec - 5 min depending on platforms)

## 📋 Next Steps

- **Review**: Check **📋 Job Feed** for scored jobs
- **Apply**: Add to **🤖 Apply Queue** and apply
- **Track**: Monitor **📊 Tracker**

## ⚡ Tips for Faster Results

Use **fast platforms only** for quick search:
```yaml
portals:
  - naukri
  - greenhouse
  - lever
```

Skip LinkedIn in config.yaml if you want <1 min searches.

## 🔧 Troubleshooting

| Problem | Solution |
|---------|----------|
| "GEMINI_API_KEY not set" | Check `.env` file exists and has API key |
| "Playwright not installed" | Run `playwright install chromium` |
| "No jobs found" | Lower score_threshold in config.yaml to 40% |
| LinkedIn login fails | Check email/password in `.env`, disable 2FA |
| Search hanging | Check internet speed, disable LinkedIn |

## 📚 Full Docs

See [README.md](README.md) for complete documentation.

---

**That's it! Happy job hunting! 🎯**
