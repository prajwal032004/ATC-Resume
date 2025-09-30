import os
import PyPDF2
import pdfkit
import platform
from flask import Flask, render_template, request, jsonify, session, Response
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

# Import AI utility functions
from utils.ai import (
    generate_professional_summary,
    analyze_resume_text,
    generate_cover_letter,
    match_jobs,
    analyze_skill_gap,
    generate_app_description
)

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_SECRET_KEY", "your-secret-key-here")
app.config['UPLOAD_FOLDER'] = 'Uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize CSRF protection
csrf = CSRFProtect(app)

# --- wkhtmltopdf Configuration ---
def configure_wkhtmltopdf():
    """Configure wkhtmltopdf based on the operating system."""
    if platform.system() == "Windows":
        possible_paths = [
            r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe',
            r'C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe'
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return pdfkit.configuration(wkhtmltopdf=path)
        print("WARNING: wkhtmltopdf.exe not found. PDF generation will fail.")
        return None
    else:  # macOS, Linux
        possible_paths = [
            '/usr/local/bin/wkhtmltopdf',
            '/usr/bin/wkhtmltopdf'
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return pdfkit.configuration(wkhtmltopdf=path)
        print("WARNING: wkhtmltopdf not found. PDF generation will fail.")
        return None

config = configure_wkhtmltopdf()

# --- Page Routes ---

@app.route('/')
def index():
    """Home page route."""
    return render_template('index.html')

@app.route('/resume-builder', methods=['GET', 'POST'])
def resume_builder():
    """Resume builder page route."""
    if request.method == 'POST':
        session['resume_data'] = request.form.to_dict(flat=False)
        return render_template('resume_preview.html', data=session['resume_data'])
    return render_template('resume_builder.html')

@app.route('/resume-analyzer')
def resume_analyzer_page():
    """Resume analyzer page route."""
    return render_template('resume_analyzer.html')

@app.route('/cover-letter-generator')
def cover_letter_page():
    """Cover letter generator page route."""
    return render_template('cover_letter_generator.html')

@app.route('/job-matcher')
def job_matcher_page():
    """Job matcher page route."""
    return render_template('job_matcher.html')
    
@app.route('/skill-gap-analyzer')
def skill_gap_page():
    """Skill gap analyzer page route."""
    return render_template('skill_gap_analyzer.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    """Contact page route with form submission handling."""
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            email = request.form.get('email')
            message = request.form.get('message')
            if not all([name, email, message]):
                return jsonify({'error': 'All fields are required.'}), 400
            
            # Placeholder for actual form submission logic (e.g., save to database, send email)
            print(f"Contact Form Submission: Name={name}, Email={email}, Message={message}")
            return jsonify({'message': 'Your message has been sent successfully!'})
        except Exception as e:
            print(f"Contact form error: {e}")
            return jsonify({'error': 'Failed to send message. Please try again.'}), 500
    return render_template('contact.html')

@app.route('/about')
def about():
    """About page route."""
    return render_template('about.html')

@app.route('/privacy-policy')
def privacy():
    """Privacy policy page route."""
    return render_template('privacy.html')

@app.route('/terms-of-service')
def terms():
    """Terms of service page route."""
    return render_template('terms.html')

# --- PDF Generation ---

@app.route('/download-pdf')
def download_pdf():
    """Generate and download PDF resume."""
    resume_data = session.get('resume_data')
    if not resume_data:
        return jsonify({'error': 'No resume data found in session.'}), 400

    rendered_html = render_template('resume_template.html', data=resume_data)
    
    if config is None:
        return jsonify({'error': 'PDF generation is not available. wkhtmltopdf is not properly configured.'}), 500

    try:
        pdf = pdfkit.from_string(
            rendered_html, 
            False, 
            configuration=config, 
            options={
                "enable-local-file-access": "",
                "page-size": "A4",
                "margin-top": "0.75in",
                "margin-right": "0.75in",
                "margin-bottom": "0.75in",
                "margin-left": "0.75in",
                "encoding": "UTF-8",
                "no-outline": None
            }
        )
        
        return Response(
            pdf,
            mimetype='application/pdf',
            headers={'Content-Disposition': 'attachment;filename=resume.pdf'}
        )
    except Exception as e:
        print(f"PDF generation error: {e}")
        return jsonify({'error': 'Error generating PDF. Please try again.'}), 500

# --- API Endpoints for AI Features ---

@app.route('/api/generate-about', methods=['POST'])
def generate_about_api():
    """Generate app description for About Us page."""
    try:
        description = generate_app_description()
        return jsonify({'description': description})
    except Exception as e:
        print(f"Error generating about description: {e}")
        return jsonify({'error': 'Failed to generate description'}), 500

@app.route('/api/chatbot', methods=['POST'])
@csrf.exempt  # Exempt CSRF for chatbot to simplify testing (remove in production with proper CSRF handling)
def chatbot():
    """Simple chatbot API endpoint."""
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'Message is required'}), 400
            
        user_message = data.get('message', '').lower().strip()
        
        # Simple rule-based responses
        if any(phrase in user_message for phrase in ["who built", "who made", "who created", "developer", "author"]):
            response_text = "This website was built by Prajwal A Bhandagi, a developer passionate about helping job seekers succeed!"
        elif any(phrase in user_message for phrase in ["help", "what can you do", "features"]):
            response_text = "I can help you with resume building, analysis, cover letter generation, job matching, and skill gap analysis. Navigate through the menu to explore all features!"
        elif any(phrase in user_message for phrase in ["resume", "cv"]):
            response_text = "I can help you build professional resumes, analyze them for ATS compatibility, and provide improvement suggestions. Try the Resume Builder or Resume Analyzer!"
        elif any(phrase in user_message for phrase in ["cover letter"]):
            response_text = "I can generate personalized cover letters based on your resume. Check out the Cover Letter Generator!"
        elif any(phrase in user_message for phrase in ["job", "career", "work"]):
            response_text = "I can help match you with suitable job roles and analyze skill gaps. Try the Job Matcher and Skill Gap Analyzer!"
        elif any(phrase in user_message for phrase in ["hello", "hi", "hey"]):
            response_text = "Hello! Welcome to ATC Resume Builder. I'm here to help you with your career development. How can I assist you today?"
        elif any(phrase in user_message for phrase in ["thank", "thanks"]):
            response_text = "You're welcome! Feel free to explore all the features and let me know if you need any help."
        else:
            response_text = "I'm here to help with resume building, career guidance, and job search tools. You can ask me about features, who built this site, or navigate through the menu to explore all available tools!"
        
        return jsonify({'reply': response_text})
        
    except Exception as e:
        print(f"Chatbot error: {e}")
        return jsonify({'error': 'Sorry, I encountered an error. Please try again.'}), 500

@app.route('/api/expand-summary', methods=['POST'])
def expand_summary():
    """Expand a short summary into a professional one."""
    try:
        data = request.get_json()
        if not data or 'summary' not in data:
            return jsonify({'error': 'Summary text is required.'}), 400
            
        short_summary = data.get('summary', '').strip()
        if not short_summary:
            return jsonify({'error': 'Summary text cannot be empty.'}), 400
            
        expanded_summary = generate_professional_summary(short_summary)
        return jsonify({'expanded_summary': expanded_summary})
        
    except Exception as e:
        print(f"Error expanding summary: {e}")
        return jsonify({'error': 'Failed to expand summary'}), 500

def process_resume_upload(tool_function):
    """Helper function to process resume uploads for various AI tools."""
    try:
        if 'resume' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
            
        file = request.files['resume']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Invalid file type. Please upload a PDF file.'}), 400
        
        # Save and process the file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Extract text from PDF
        text = ""
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        
        # Clean up the file
        os.remove(filepath)
        
        if not text.strip():
            return jsonify({'error': 'Could not extract text from the PDF. The file might be image-based or corrupted.'}), 400
        
        # Process with AI
        result = tool_function(text)
        return jsonify({'result': result})
        
    except Exception as e:
        print(f"File processing error: {e}")
        # Clean up file if it exists
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': 'Failed to process the file. Please try again.'}), 500

@app.route('/api/analyze-resume', methods=['POST'])
def analyze_resume_api():
    """Analyze resume for ATS compatibility and improvements."""
    return process_resume_upload(analyze_resume_text)

@app.route('/api/generate-cover-letter', methods=['POST'])
def generate_cover_letter_api():
    """Generate cover letter based on resume."""
    return process_resume_upload(generate_cover_letter)

@app.route('/api/match-jobs', methods=['POST'])
def match_jobs_api():
    """Match jobs based on resume skills."""
    return process_resume_upload(match_jobs)

@app.route('/api/analyze-skill-gap', methods=['POST'])
def analyze_skill_gap_api():
    """Analyze skill gaps in resume."""
    return process_resume_upload(analyze_skill_gap)

# --- Error Handlers ---

@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors."""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)