# ATC Resume Builder

A comprehensive AI-powered web application for building professional resumes, analyzing them for ATS compatibility, generating cover letters, matching jobs, and identifying skill gaps.

## 🌟 Features

### Core Features
- **Resume Builder**: Create professional resumes with an intuitive form-based interface
- **Resume Analyzer**: Analyze resumes for ATS (Applicant Tracking System) compatibility
- **Cover Letter Generator**: Generate personalized cover letters based on your resume
- **Job Matcher**: Match your skills with suitable job roles
- **Skill Gap Analyzer**: Identify skill gaps and get recommendations for improvement
- **AI Chatbot**: Get instant help and guidance on using the platform
- **PDF Generation**: Download your resume as a professional PDF document

### Additional Features
- Professional summary expansion using AI
- Dynamic about page content generation
- Contact form for user inquiries
- Privacy policy and terms of service pages
- Responsive design for mobile and desktop
- CSRF protection for secure form submissions

## 🚀 Getting Started

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- wkhtmltopdf (for PDF generation)

#### Installing wkhtmltopdf

**Windows:**
```bash
# Download and install from: https://wkhtmltopdf.org/downloads.html
# Default installation path: C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe
```
or
```
pip install wkhtmltopdf
```

**macOS:**
```bash
brew install wkhtmltopdf
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install wkhtmltopdf
```

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/prajwal032004/ATC-Resume.git
cd ATC-Resume
```

2. **Create a virtual environment**
```bash
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate

# macOS/Linux:
source venv/bin/activate
```

3. **Install required packages**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**

Create a `.env` file in the root directory:
```env
FLASK_SECRET_KEY=your-secret-key-here
GEMINI_API_KEY=your-gemini-api-key
# Add other API keys as needed
```

5. **Create necessary directories**
```bash
mkdir Uploads
```

6. **Run the application**
```bash
python app.py
```

The application will be available at `http://localhost:5000`

## 📦 Requirements

Create a `requirements.txt` file with the following dependencies:

```txt
Flask==2.3.0
PyPDF2==3.0.0
pdfkit==1.0.0
python-dotenv==1.0.0
Flask-WTF==1.1.1
Werkzeug==2.3.0
anthropic==0.25.0
# Add other dependencies as needed
```

## 🗂️ Project Structure

```
ATC-Resume/
│
├── app.py                          # Main application file
├── requirements.txt                # Python dependencies
├── .env                           # Environment variables (not in repo)
│
├── utils/
│   └── ai.py                      # AI utility functions
│
├── templates/                     # HTML templates
│   ├── index.html                # Home page
│   ├── resume_builder.html       # Resume builder form
│   ├── resume_preview.html       # Resume preview
│   ├── resume_template.html      # PDF template
│   ├── resume_analyzer.html      # Resume analyzer page
│   ├── cover_letter_generator.html
│   ├── job_matcher.html
│   ├── skill_gap_analyzer.html
│   ├── contact.html
│   ├── about.html
│   ├── privacy.html
│   ├── terms.html
│   ├── 404.html                  # Error pages
│   └── 500.html
│
├── static/                        # Static files
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   └── scripts.js
│   └── images/
│
└── Uploads/                       # Temporary file uploads (gitignored)
```

## 🔧 Configuration

### AI Configuration

The application uses AI services for various features. Configure your AI API keys in the `.env` file:

```env
GEMINI_API_KEY=your-api-key-here
```

### wkhtmltopdf Configuration

The application automatically detects wkhtmltopdf installation. If you have a custom installation path, modify the `configure_wkhtmltopdf()` function in `app.py`.

## 📖 API Endpoints

### Page Routes
- `GET /` - Home page
- `GET /resume-builder` - Resume builder form
- `POST /resume-builder` - Submit resume data
- `GET /resume-analyzer` - Resume analyzer page
- `GET /cover-letter-generator` - Cover letter generator
- `GET /job-matcher` - Job matcher page
- `GET /skill-gap-analyzer` - Skill gap analyzer
- `GET /contact` - Contact page
- `POST /contact` - Submit contact form
- `GET /about` - About page
- `GET /privacy-policy` - Privacy policy
- `GET /terms-of-service` - Terms of service

### API Endpoints
- `POST /api/generate-about` - Generate about page content
- `POST /api/chatbot` - Chatbot interaction
- `POST /api/expand-summary` - Expand professional summary
- `POST /api/analyze-resume` - Analyze resume (PDF upload)
- `POST /api/generate-cover-letter` - Generate cover letter (PDF upload)
- `POST /api/match-jobs` - Match jobs (PDF upload)
- `POST /api/analyze-skill-gap` - Analyze skill gaps (PDF upload)
- `GET /download-pdf` - Download resume as PDF

## 🛡️ Security Features

- CSRF protection using Flask-WTF
- Secure file upload handling with filename sanitization
- Session-based data storage
- Environment variable protection for sensitive keys
- File cleanup after processing

## 🎨 Customization

### Modifying Resume Templates

Edit `templates/resume_template.html` to customize the PDF resume layout.

### Styling

Modify `static/css/styles.css` to change the application's appearance.

### AI Responses

Update the AI utility functions in `utils/ai.py` to customize AI behavior and responses.

## 🐛 Troubleshooting

### PDF Generation Issues

**Error: wkhtmltopdf not found**
- Ensure wkhtmltopdf is installed correctly
- Verify the installation path matches the configuration
- Check system PATH environment variable

**Error: PDF generation failed**
- Check wkhtmltopdf permissions
- Verify the template HTML is valid
- Review application logs for detailed errors

### File Upload Issues

**Error: Could not extract text from PDF**
- Ensure the PDF is not password-protected
- Check if the PDF contains actual text (not scanned images)
- Try re-saving the PDF from another source

### AI Features Not Working

- Verify API keys are correctly set in `.env`
- Check internet connection for API calls
- Review API usage limits and quotas

## 📝 License

This project is licensed under the Self License.

## 👨‍💻 Author

**Prajwal A Bhandagi**

- GitHub: [@prajwal032004](https://github.com/prajwal032004)
- Project Link: [https://github.com/prajwal032004/ATC-Resume](https://github.com/prajwal032004/ATC-Resume)

## 🙏 Acknowledgments

- Flask framework for the web application structure
- PyPDF2 for PDF text extraction
- pdfkit and wkhtmltopdf for PDF generation
- Anthropic Claude for AI-powered features
- All contributors and users of this project

## 🔮 Future Enhancements

- [ ] Multiple resume templates
- [ ] LinkedIn profile import
- [ ] Real-time collaboration
- [ ] Resume version history
- [ ] Job application tracking
- [ ] Interview preparation tools
- [ ] Salary negotiation guidance
- [ ] Multi-language support

---

**Note**: This is an educational project. For production use, ensure proper security measures, error handling, and scalability considerations are implemented.

Made with ❤️ by Prajwal A Bhandagi
