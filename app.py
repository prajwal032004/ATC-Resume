from flask import Flask, render_template, request, send_file, redirect, url_for, flash, session, Response, jsonify
import pdfkit
from pdfkit.configuration import Configuration
import os
import json
from datetime import datetime
import uuid
import logging
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import csv
from io import StringIO
import smtplib
from email.mime.text import MIMEText
import random
import pdfplumber
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io
import base64
import google.generativeai as genai
from werkzeug.utils import secure_filename
import re
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
try:
    from PIL import Image
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    pytesseract = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_for_testing')

# Gmail credentials for OTP
EMAIL_ADDRESS = "--------------------.com"
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '---- ---- ---- ----')

# Hardcoded admin credentials
ADMIN_USERNAME = "-------"
ADMIN_PASSWORD_HASH = generate_password_hash("--------")

# In-memory stores
logged_in_users = {}
otp_storage = {}

# Gemini API key
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', 'Your GEMINI Key')
if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not set")
    raise ValueError("GEMINI_API_KEY is required")
genai.configure(api_key=GEMINI_API_KEY)

# Directory for uploaded resumes
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Database initialization
def init_db():
    try:
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS contact_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                user_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise
    finally:
        conn.close()

init_db()

# Admin-required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        if session.get('is_admin', False):
            return f(*args, **kwargs)
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],))
        user = c.fetchone()
        conn.close()
        if not user or not user[0]:
            flash('You do not have permission to access this page.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Configure wkhtmltopdf path
if os.name == 'nt':
    WKHTMLTOPDF_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
else:
    WKHTMLTOPDF_PATH = '/usr/local/bin/wkhtmltopdf'

if os.path.exists(WKHTMLTOPDF_PATH):
    config = Configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
else:
    logger.warning(f"wkhtmltopdf not found at {WKHTMLTOPDF_PATH}. PDF generation may fail.")
    config = None

os.makedirs(os.path.join('static', 'downloads'), exist_ok=True)

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.context_processor
def inject_year():
    return {'year': datetime.now().year}

@app.route('/')
def index():
    try:
        logger.info(f"Rendering index.html for user_id: {session.get('user_id', 'None')}")
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index.html: {str(e)}")
        flash('An error occurred while loading the page.', 'error')
        return render_template('error.html', error="Failed to load homepage")

@app.route('/blog')
def blog():
    return render_template('blog.html')

@app.route('/resume_tips')
def tips():
    return render_template('tips.html')

@app.route('/support')
def support():
    return render_template('support.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/terms-of-service')
def terms_of_service():
    return render_template('terms_of_service.html')

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacy_policy.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')

        if not email or not password or not full_name:
            flash('All fields are required.', 'error')
            return redirect(url_for('register'))

        try:
            conn = sqlite3.connect('resume_builder.db')
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE email = ?', (email,))
            if c.fetchone():
                flash('Email already registered.', 'error')
                return redirect(url_for('register'))

            otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            otp_storage[email] = {'otp': otp, 'password': generate_password_hash(password), 'full_name': full_name}

            subject = "Your OTP for ATC Resume Builder Registration"
            body = f"Hi {full_name},\nYour OTP is: {otp}\nPlease use this to complete your registration.\nThis OTP expires in 10 minutes."
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = EMAIL_ADDRESS
            msg['To'] = email

            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.send_message(msg)

            flash('An OTP has been sent to your email.', 'success')
            return redirect(url_for('verify_otp', email=email))
        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            flash('An error occurred during registration.', 'error')
            return redirect(url_for('register'))
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = request.args.get('email')
    if not email or email not in otp_storage:
        flash('Invalid or expired OTP request.', 'error')
        return redirect(url_for('register'))

    if request.method == 'POST':
        otp = request.form.get('otp')
        if otp == otp_storage[email]['otp']:
            try:
                conn = sqlite3.connect('resume_builder.db')
                c = conn.cursor()
                c.execute('INSERT INTO users (email, password, full_name) VALUES (?, ?, ?)',
                         (email, otp_storage[email]['password'], otp_storage[email]['full_name']))
                conn.commit()
                del otp_storage[email]
                flash('Registration successful! Please log in.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                logger.error(f"OTP verification error: {str(e)}")
                flash('An error occurred during verification.', 'error')
                return redirect(url_for('register'))
            finally:
                conn.close()
        else:
            flash('Invalid OTP. Please try again.', 'error')
            return redirect(url_for('verify_otp', email=email))
    return render_template('verify_otp.html', email=email)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('login'))

        try:
            conn = sqlite3.connect('resume_builder.db')
            c = conn.cursor()
            c.execute('SELECT id, password, full_name, is_admin FROM users WHERE email = ?', (email,))
            user = c.fetchone()

            if user and check_password_hash(user[1], password):
                session['user_id'] = user[0]
                session['user_email'] = email
                session['user_name'] = user[2]
                session['is_admin'] = user[3] if user[3] is not None else 0
                logged_in_users[user[0]] = {'name': user[2], 'email': email}
                flash('Login successful!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid email or password.', 'error')
                return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login.', 'error')
            return redirect(url_for('login'))
        finally:
            conn.close()
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Email is required.', 'error')
            return redirect(url_for('forgot_password'))

        try:
            conn = sqlite3.connect('resume_builder.db')
            c = conn.cursor()
            c.execute('SELECT id FROM users WHERE email = ?', (email,))
            user = c.fetchone()

            if user:
                otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
                otp_storage[email] = {'otp': otp, 'user_id': user[0]}

                subject = "Your OTP for Password Reset"
                body = f"Your OTP is: {otp}\nUse this to reset your password.\nThis OTP expires in 10 minutes."
                msg = MIMEText(body)
                msg['Subject'] = subject
                msg['From'] = EMAIL_ADDRESS
                msg['To'] = email

                with smtplib.SMTP('smtp.gmail.com', 587) as server:
                    server.starttls()
                    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                    server.send_message(msg)

                flash('An OTP has been sent to your email.', 'success')
                return redirect(url_for('reset_password', email=email))
            else:
                flash('Email not found.', 'error')
                return redirect(url_for('forgot_password'))
        except Exception as e:
            logger.error(f"Forgot password error: {str(e)}")
            flash('An error occurred. Please try again.', 'error')
            return redirect(url_for('forgot_password'))
        finally:
            conn.close()
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = request.args.get('email')
    if not email or email not in otp_storage:
        flash('Invalid or expired reset request.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        otp = request.form.get('otp')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not otp or not new_password or not confirm_password:
            flash('All fields are required.', 'error')
            return redirect(url_for('reset_password', email=email))

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', email=email))

        if otp == otp_storage[email]['otp']:
            try:
                conn = sqlite3.connect('resume_builder.db')
                c = conn.cursor()
                c.execute('UPDATE users SET password = ? WHERE email = ?',
                         (generate_password_hash(new_password), email))
                conn.commit()
                del otp_storage[email]
                flash('Password reset successful! Please log in.', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                logger.error(f"Password reset error: {str(e)}")
                flash('An error occurred during password reset.', 'error')
                return redirect(url_for('forgot_password'))
            finally:
                conn.close()
        else:
            flash('Invalid OTP. Please try again.', 'error')
            return redirect(url_for('reset_password', email=email))
    return render_template('reset_password.html', email=email)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required.', 'error')
            return redirect(url_for('admin_login'))

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['user_id'] = 0
            session['is_admin'] = True
            session['user_name'] = 'Admin'
            session['user_email'] = 'admin@example.com'
            logged_in_users[0] = {'name': 'Admin', 'email': 'admin@example.com'}
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials.', 'error')
            return redirect(url_for('admin_login'))
    return render_template('admin_login.html')

@app.route('/logout')
def logout():
    user_id = session.get('user_id')
    if user_id in logged_in_users:
        del logged_in_users[user_id]
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/build-resume')
@login_required
def build_resume():
    return render_template('resume_form.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/submit-contact', methods=['POST'])
def submit_contact():
    try:
        first_name = request.form.get('first_name', '')
        last_name = request.form.get('last_name', '')
        email = request.form.get('email', '')
        phone = request.form.get('phone', '')
        message = request.form.get('message', '')
        
        if not all([first_name, last_name, email, message]):
            flash('All fields are required.', 'error')
            return redirect(url_for('contact'))
            
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO contact_messages 
            (first_name, last_name, email, phone, message) 
            VALUES (?, ?, ?, ?, ?)
        ''', (first_name, last_name, email, phone, message))
        conn.commit()
        conn.close()
        
        flash('Your message has been sent successfully!', 'success')
        return redirect(url_for('contact'))
    except Exception as e:
        logger.error(f"Error in submit_contact: {str(e)}")
        flash('An error occurred while sending your message.', 'error')
        return redirect(url_for('contact'))

@app.route('/preview', methods=['POST'])
@login_required
def preview_resume():
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    email = request.form.get('email', '')
    phone = request.form.get('phone', '')
    location = request.form.get('location', '')
    
    education = []
    edu_institutions = request.form.getlist('edu_institution')
    edu_degrees = request.form.getlist('edu_degree')
    edu_majors = request.form.getlist('edu_major')
    edu_locations = request.form.getlist('edu_location')
    edu_start_dates = request.form.getlist('edu_start_date')
    edu_end_dates = request.form.getlist('edu_end_date')
    edu_gpas = request.form.getlist('edu_gpa')
    edu_courseworks = request.form.getlist('edu_coursework')
    
    for i in range(len(edu_institutions)):
        if edu_institutions[i]:
            education.append({
                'institution': edu_institutions[i],
                'degree': edu_degrees[i],
                'major': edu_majors[i],
                'location': edu_locations[i],
                'start_date': edu_start_dates[i],
                'end_date': edu_end_dates[i],
                'gpa': edu_gpas[i],
                'coursework': edu_courseworks[i]
            })
    
    experience = []
    exp_companies = request.form.getlist('exp_company')
    exp_titles = request.form.getlist('exp_title')
    exp_locations = request.form.getlist('exp_location')
    exp_start_dates = request.form.getlist('exp_start_date')
    exp_end_dates = request.form.getlist('exp_end_date')
    exp_descriptions = request.form.getlist('exp_description')
    
    for i in range(len(exp_companies)):
        if exp_companies[i]:
            bullets = [bullet.strip() for bullet in exp_descriptions[i].split('\n') if bullet.strip()]
            experience.append({
                'company': exp_companies[i],
                'title': exp_titles[i],
                'location': exp_locations[i],
                'start_date': exp_start_dates[i],
                'end_date': exp_end_dates[i],
                'bullets': bullets
            })
    
    projects = []
    proj_titles = request.form.getlist('proj_title')
    proj_dates = request.form.getlist('proj_date')
    proj_descriptions = request.form.getlist('proj_description')
    
    for i in range(len(proj_titles)):
        if proj_titles[i]:
            bullets = [bullet.strip() for bullet in proj_descriptions[i].split('\n') if bullet.strip()]
            projects.append({
                'title': proj_titles[i],
                'date': proj_dates[i],
                'bullets': bullets
            })
    
    activities = []
    act_organizations = request.form.getlist('act_organization')
    act_roles = request.form.getlist('act_role')
    act_locations = request.form.getlist('act_location')
    act_start_dates = request.form.getlist('act_start_date')
    act_end_dates = request.form.getlist('act_end_date')
    act_descriptions = request.form.getlist('act_description')
    
    for i in range(len(act_organizations)):
        if act_organizations[i]:
            bullets = [bullet.strip() for bullet in act_descriptions[i].split('\n') if bullet.strip()]
            activities.append({
                'organization': act_organizations[i],
                'role': act_roles[i],
                'location': act_locations[i],
                'start_date': act_start_dates[i],
                'end_date': act_end_dates[i],
                'bullets': bullets
            })
    
    technical_skills = request.form.get('technical_skills', '')
    languages = request.form.get('languages', '')
    certifications = request.form.get('certifications', '')
    awards = request.form.get('awards', '')
    
    resume_data = {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'location': location,
        'education': education,
        'experience': experience,
        'projects': projects,
        'activities': activities,
        'technical_skills': technical_skills,
        'languages': languages,
        'certifications': certifications,
        'awards': awards,
    }
    
    return render_template('resume_preview.html', resume=resume_data)

@app.route('/download', methods=['POST'])
@login_required
def download_resume():
    first_name = request.form.get('first_name', '')
    last_name = request.form.get('last_name', '')
    email = request.form.get('email', '')
    phone = request.form.get('phone', '')
    location = request.form.get('location', '')
    
    education = []
    edu_institutions = request.form.getlist('edu_institution')
    edu_degrees = request.form.getlist('edu_degree')
    edu_majors = request.form.getlist('edu_major')
    edu_locations = request.form.getlist('edu_location')
    edu_start_dates = request.form.getlist('edu_start_date')
    edu_end_dates = request.form.getlist('edu_end_date')
    edu_gpas = request.form.getlist('edu_gpa')
    edu_courseworks = request.form.getlist('edu_coursework')
    
    for i in range(len(edu_institutions)):
        if edu_institutions[i]:
            education.append({
                'institution': edu_institutions[i],
                'degree': edu_degrees[i],
                'major': edu_majors[i],
                'location': edu_locations[i],
                'start_date': edu_start_dates[i],
                'end_date': edu_end_dates[i],
                'gpa': edu_gpas[i],
                'coursework': edu_courseworks[i]
            })
    
    experience = []
    exp_companies = request.form.getlist('exp_company')
    exp_titles = request.form.getlist('exp_title')
    exp_locations = request.form.getlist('exp_location')
    exp_start_dates = request.form.getlist('exp_start_date')
    exp_end_dates = request.form.getlist('exp_end_date')
    exp_descriptions = request.form.getlist('exp_description')
    
    for i in range(len(exp_companies)):
        if exp_companies[i]:
            bullets = [bullet.strip() for bullet in exp_descriptions[i].split('\n') if bullet.strip()]
            experience.append({
                'company': exp_companies[i],
                'title': exp_titles[i],
                'location': exp_locations[i],
                'start_date': exp_start_dates[i],
                'end_date': exp_end_dates[i],
                'bullets': bullets
            })
    
    projects = []
    proj_titles = request.form.getlist('proj_title')
    proj_dates = request.form.getlist('proj_date')
    proj_descriptions = request.form.getlist('proj_description')
    
    for i in range(len(proj_titles)):
        if proj_titles[i]:
            bullets = [bullet.strip() for bullet in proj_descriptions[i].split('\n') if bullet.strip()]
            projects.append({
                'title': proj_titles[i],
                'date': proj_dates[i],
                'bullets': bullets
            })
    
    activities = []
    act_organizations = request.form.getlist('act_organization')
    act_roles = request.form.getlist('act_role')
    act_locations = request.form.getlist('act_location')
    act_start_dates = request.form.getlist('act_start_date')
    act_end_dates = request.form.getlist('act_end_date')
    act_descriptions = request.form.getlist('act_description')
    
    for i in range(len(act_organizations)):
        if act_organizations[i]:
            bullets = [bullet.strip() for bullet in act_descriptions[i].split('\n') if bullet.strip()]
            activities.append({
                'organization': act_organizations[i],
                'role': act_roles[i],
                'location': act_locations[i],
                'start_date': act_start_dates[i],
                'end_date': act_end_dates[i],
                'bullets': bullets
            })
    
    technical_skills = request.form.get('technical_skills', '')
    languages = request.form.get('languages', '')
    certifications = request.form.get('certifications', '')
    awards = request.form.get('awards', '')
    
    resume_data = {
        'first_name': first_name,
        'last_name': last_name,
        'email': email,
        'phone': phone,
        'location': location,
        'education': education,
        'experience': experience,
        'projects': projects,
        'activities': activities,
        'technical_skills': technical_skills,
        'languages': languages,
        'certifications': certifications,
        'awards': awards,
    }
    
    rendered_html = render_template('resume_download.html', resume=resume_data)
    filename = f"resume_{uuid.uuid4()}.pdf"
    pdf_path = os.path.join('static', 'downloads', filename)
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    
    try:
        pdfkit.from_string(rendered_html, pdf_path, options={
            'page-size': 'Letter',
            'margin-top': '0.5in',
            'margin-right': '0.5in',
            'margin-bottom': '0.5in',
            'margin-left': '0.5in',
            'encoding': 'UTF-8',
        }, configuration=config)
    except Exception as e:
        logger.error(f"PDF generation failed: {str(e)}")
        flash('An error occurred while generating the PDF.', 'error')
        return redirect(url_for('build_resume'))
    
    return send_file(pdf_path, as_attachment=True, download_name=f"{first_name}_{last_name}_Resume.pdf")

@app.route('/chatbot', methods=['GET', 'POST'])
@login_required
def chatbot():
    if request.method == 'POST':
        user_input = request.form.get('message')
        if not user_input:
            flash('Please enter a message.', 'error')
            return render_template('chatbot.html', messages=[])
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"You are a resume-building assistant. Provide concise, professional advice to help the user build a resume. User input: {user_input}"
            response = model.generate_content(prompt)
            
            if not response.text:
                flash('No response from the model. Try again.', 'error')
                return render_template('chatbot.html', messages=[])
                
            bot_response = response.text
            messages = [{'sender': 'user', 'text': user_input}, {'sender': 'bot', 'text': bot_response}]
            return render_template('chatbot.html', messages=messages)
        except Exception as e:
            logger.error(f"Chatbot error: {str(e)}")
            flash(f"An error occurred: {str(e)}", 'error')
            return render_template('chatbot.html', messages=[])
    return render_template('chatbot.html', messages=[])

@app.route('/chatbot_popup', methods=['POST'])
def chatbot_popup():
    try:
        data = request.get_json()
        user_input = data.get('message')
        if not user_input:
            return jsonify({'error': 'Please enter a message.'}), 400
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"You are a resume-building assistant. Provide concise, professional advice to help the user build a resume. User input: {user_input}"
        response = model.generate_content(prompt)
        
        if not response.text:
            return jsonify({'error': 'No response from the model. Try again.'}), 500
            
        bot_response = response.text
        logger.info(f"Chatbot popup response generated for input: {user_input[:50]}...")
        return jsonify({'response': bot_response})
    except Exception as e:
        logger.error(f"Chatbot popup error: {str(e)}")
        return jsonify({'error': 'An error occurred. Please try again later.'}), 500

@app.route('/analyze-resume', methods=['GET', 'POST'])
@login_required
def analyze_resume():
    if request.method == 'POST':
        if 'resume' not in request.files:
            flash('No file uploaded.', 'error')
            return redirect(url_for('analyze_resume'))
        
        file = request.files['resume']
        if file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('analyze_resume'))
        
        if file and file.filename.lower().endswith('.pdf'):
            if not validate_upload_folder():
                flash('Server error: Unable to process uploads.', 'error')
                return redirect(url_for('analyze_resume'))
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}_{filename}")
            
            try:
                logger.info(f"Saving file to {file_path}")
                file.save(file_path)
                
                if not os.path.exists(file_path):
                    logger.error(f"File not found after saving: {file_path}")
                    flash('Error: File could not be saved.', 'error')
                    return redirect(url_for('analyze_resume'))
                
                text = ""
                try:
                    logger.info(f"Extracting text from {file_path}")
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            page_text = page.extract_text()
                            if page_text:
                                text += page_text + "\n"
                    if len(text.strip()) < 100 and OCR_AVAILABLE:
                        logger.info("Minimal text extracted, attempting OCR")
                        with pdfplumber.open(file_path) as pdf:
                            for page in pdf.pages:
                                img = page.to_image(resolution=300).original
                                page_text = pytesseract.image_to_string(img, lang='eng')
                                if page_text:
                                    text += page_text + "\n"
                except Exception as e:
                    logger.error(f"PDF extraction error: {str(e)}")
                    flash('Error extracting text from PDF.', 'error')
                    return redirect(url_for('analyze_resume'))
                
                if not text or len(text.strip()) < 50:
                    flash('Could not extract enough text.', 'error')
                    return redirect(url_for('analyze_resume'))
                
                logger.info("Parsing resume content")
                try:
                    resume_data = parse_resume_content(text)
                except Exception as e:
                    logger.error(f"Error parsing resume: {str(e)}")
                    flash('Error parsing resume content.', 'error')
                    return redirect(url_for('analyze_resume'))
                
                career_field = request.form.get('career_field', 'General')
                
                logger.info("Generating AI analysis")
                try:
                    analysis = generate_resume_analysis(text, resume_data, career_field)
                except Exception as e:
                    logger.error(f"Error generating analysis: {str(e)}")
                    analysis = {
                        'overall_impression': 'Unable to analyze.',
                        'field_alignment': 0,
                        'strengths': [],
                        'weaknesses': [],
                        'ats_compatibility': 0,
                        'career_level': 'Unknown',
                        'top_skills': [],
                        'industry_fit': [],
                        'action_items': []
                    }
                
                job_title = request.form.get('job_title', '')
                industry = request.form.get('industry', '')
                skill_match = {}
                if job_title:
                    logger.info(f"Generating skill match for {job_title}")
                    try:
                        skill_match = generate_skill_match(text, job_title, industry, career_field)
                    except Exception as e:
                        logger.error(f"Error generating skill match: {str(e)}")
                        skill_match = {
                            'match_percentage': 0,
                            'technical_skill_match': 'unknown',
                            'soft_skill_match': 'unknown',
                            'industry_knowledge': 'unknown',
                            'key_skills_for_role': [],
                            'matching_skills': [],
                            'missing_skills': [],
                            'improvement_suggestions': []
                        }
                
                logger.info("Generating resume stats")
                try:
                    stats = calculate_resume_stats(resume_data, career_field)
                    plot_url = generate_resume_charts(stats)
                except Exception as e:
                    logger.error(f"Error generating stats/charts: {str(e)}")
                    stats = {
                        'years_experience': 0,
                        'skill_count': 0,
                        'education_level': 'Unknown',
                        'project_count': 0,
                        'cert_count': 0,
                        'publication_count': 0,
                        'patent_count': 0,
                        'language_count': 0,
                        'avg_job_tenure': 0,
                        'skill_distribution': {}
                    }
                    plot_url = ""
                
                logger.info("Generating field recommendations")
                try:
                    field_recommendations = generate_field_recommendations(text, resume_data, career_field)
                except Exception as e:
                    logger.error(f"Error generating recommendations: {str(e)}")
                    field_recommendations = {
                        'industry_trends': [],
                        'key_certifications': [],
                        'technical_skills': [],
                        'resume_format': 'No recommendations available.',
                        'portfolio_tips': 'No tips available.'
                    }
                
                logger.info("Generating keyword analysis")
                try:
                    keyword_analysis = analyze_resume_keywords(text, career_field)
                except Exception as e:
                    logger.error(f"Error generating keyword analysis: {str(e)}")
                    keyword_analysis = {
                        'top_keywords': [],
                        'missing_keywords': [],
                        'keyword_density': 'unknown',
                        'ats_tips': []
                    }
                
                logger.info("Checking international compatibility")
                try:
                    international_compatibility = check_international_compatibility(text, resume_data)
                except Exception as e:
                    logger.error(f"Error checking compatibility: {str(e)}")
                    international_compatibility = {
                        'global_compatibility': 0,
                        'us_compatibility': 'unknown',
                        'europe_compatibility': 'unknown',
                        'asia_compatibility': 'unknown',
                        'recommendations': []
                    }
                
                logger.info("Generating personality assessment")
                try:
                    personality_assessment = assess_personality_traits(text)
                except Exception as e:
                    logger.error(f"Error generating personality assessment: {str(e)}")
                    personality_assessment = {
                        'leadership': {'score': 'unknown', 'evidence': ''},
                        'teamwork': {'score': 'unknown', 'evidence': ''},
                        'initiative': {'score': 'unknown', 'evidence': ''},
                        'adaptability': {'score': 'unknown', 'evidence': ''},
                        'attention_to_detail': {'score': 'unknown', 'evidence': ''},
                        'recommendations': []
                    }
                
                if 'user_id' in session:
                    try:
                        conn = sqlite3.connect('resume_builder.db')
                        c = conn.cursor()
                        c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                                 (f"Analyzed resume for {career_field}", session['user_id']))
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        logger.warning(f"Failed to log activity: {str(e)}")
                
                logger.info("Rendering analysis template")
                return render_template('resume_analysis.html',
                                    resume_data=resume_data,
                                    analysis=analysis,
                                    skill_match=skill_match,
                                    stats=stats,
                                    plot_url=plot_url,
                                    job_title=job_title,
                                    industry=industry,
                                    career_field=career_field,
                                    field_recommendations=field_recommendations,
                                    keyword_analysis=keyword_analysis,
                                    international_compatibility=international_compatibility,
                                    personality_assessment=personality_assessment)
                                    
            except Exception as e:
                logger.error(f"Resume analysis error: {str(e)}")
                flash(f"Error analyzing resume: {str(e)}", 'error')
                return redirect(url_for('analyze_resume'))
            finally:
                if os.path.exists(file_path):
                    try:
                        logger.info(f"Deleting file: {file_path}")
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete file: {str(e)}")
        else:
            flash('Only PDF files allowed.', 'error')
            return redirect(url_for('analyze_resume'))
    
    industries = [
        "Technology", "Finance", "Healthcare", "Education", "Manufacturing",
        "Retail", "Marketing", "Engineering", "Consulting", "Government",
        "Non-profit", "Other"
    ]
    career_fields = [
        "Software Engineering", "Mechanical Engineering", "Civil Engineering",
        "Electrical Engineering", "Business & Management", "Healthcare & Medicine",
        "Arts & Design", "Education & Teaching", "Finance & Accounting", "Legal",
        "Marketing & Sales", "Human Resources", "Research & Science", "General"
    ]
    return render_template('resume_upload.html', industries=industries, career_fields=career_fields)

# Helper functions for resume analysis
import re
import logging

logging.basicConfig(filename='resume_analyzer.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def parse_resume_content(text, analysis_text=''):
    resume_data = {
        'contact_info': {'name': '', 'email': '', 'phone': '', 'location': '', 'links': []},
        'education': [], 'experience': [], 'skills': [], 'projects': [],
        'certifications': [], 'publications': [], 'patents': [], 'workshops': [],
        'languages': [], 'professional_memberships': []
    }
    
    # Normalize text and split into lines
    text = re.sub(r'\s+', ' ', text).strip()
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Log first 20 lines for debugging
    logger.info(f"First 20 lines of resume text: {lines[:20]}")
    logger.info(f"Analysis text provided: {analysis_text[:100]}...")  # Limit for brevity
    
    # Patterns for parsing
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'(?:\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}'
    url_pattern = r'(https?://[^\s]+)'
    date_pattern = r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)?\s*\d{4}\s*(?:-|–|to)?\s*(?:Present|Current|Now|\d{4})?'
    gpa_pattern = r'GPA\s*[:\-\s]\s*(\d\.\d{1,2})'
    
    # Step 1: Extract contact info (name, email, phone, links)
    for line in lines[:20]:
        line_lower = line.lower().strip()
        logger.info(f"Processing line for contact info: '{line}'")
        
        # Name extraction
        if not resume_data['contact_info']['name']:
            words = line.split()
            if (1 <= len(words) <= 10 and
                len(line) < 100 and
                not re.search(email_pattern, line_lower) and
                not re.search(phone_pattern, line_lower) and
                not re.search(url_pattern, line_lower) and
                not any(keyword in line_lower for keyword in [
                    'objective', 'summary', 'education', 'experience', 'skills', 
                    'project', 'certification', 'publication', 'patent', 'workshop',
                    'language', 'membership', 'references', 'address', 'phone', 'email',
                    'career', 'profile', 'goal', 'qualification'
                ])):
                resume_data['contact_info']['name'] = line.strip()
                logger.info(f"Directly extracted name: '{resume_data['contact_info']['name']}'")
        
        # Email, phone, links
        if not resume_data['contact_info']['email']:
            email_match = re.search(email_pattern, line)
            if email_match:
                resume_data['contact_info']['email'] = email_match.group(0)
                logger.info(f"Extracted email: '{resume_data['contact_info']['email']}'")
        if not resume_data['contact_info']['phone']:
            phone_match = re.search(phone_pattern, line)
            if phone_match:
                resume_data['contact_info']['phone'] = phone_match.group(0)
                logger.info(f"Extracted phone: '{resume_data['contact_info']['phone']}'")
        url_match = re.search(url_pattern, line)
        if url_match:
            url = url_match.group(0)
            url_type = 'Website'
            if 'linkedin.com' in url_lower:
                url_type = 'LinkedIn'
            elif 'github.com' in url_lower:
                url_type = 'GitHub'
            resume_data['contact_info']['links'].append({'type': url_type, 'url': url})
            logger.info(f"Extracted link: '{url}' as '{url_type}'")
        # Location (basic heuristic)
        if not resume_data['contact_info']['location'] and ',' in line and len(line) < 50:
            if not (re.search(email_pattern, line_lower) or re.search(phone_pattern, line_lower) or re.search(url_pattern, line_lower)):
                resume_data['contact_info']['location'] = line.strip()
                logger.info(f"Extracted location: '{resume_data['contact_info']['location']}'")
    
    # Fallbacks for name
    if not resume_data['contact_info']['name'] and analysis_text:
        name_match = re.search(r"(\w+)'s resume", analysis_text, re.IGNORECASE)
        if name_match:
            resume_data['contact_info']['name'] = name_match.group(1)
            logger.info(f"Fallback: Extracted name from analysis text: '{resume_data['contact_info']['name']}'")
    
    if not resume_data['contact_info']['name'] and resume_data['contact_info']['email']:
        email_name = resume_data['contact_info']['email'].split('@')[0]
        email_name = re.sub(r'[0-9._]+$', '', email_name).capitalize()
        if len(email_name) >= 2:
            resume_data['contact_info']['name'] = email_name
            logger.info(f"Fallback: Inferred name from email: '{resume_data['contact_info']['name']}'")
    
    # Step 2: Parse other sections
    current_section = None
    current_item = {}
    
    for line_idx, line in enumerate(lines):
        line_lower = line.lower().strip()
        logger.debug(f"Processing line for sections: '{line}'")
        
        # Detect section headers
        if len(line) < 50:
            if any(keyword in line_lower for keyword in ['experience', 'employment', 'work', 'professional', 'internship']):
                current_section = 'experience'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['education', 'academic', 'qualification']):
                current_section = 'education'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif 'skills' in line_lower:
                current_section = 'skills'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['project', 'projects']):
                current_section = 'projects'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['certification', 'certifications']):
                current_section = 'certifications'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['publication', 'publications']):
                current_section = 'publications'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['patent', 'patents']):
                current_section = 'patents'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['workshop', 'workshops', 'training']):
                current_section = 'workshops'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['language', 'languages']):
                current_section = 'languages'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
            elif any(keyword in line_lower for keyword in ['membership', 'memberships', 'affiliation']):
                current_section = 'professional_memberships'
                if current_item:
                    resume_data[current_section].append(current_item)
                    current_item = {}
                logger.info(f"Switched to section: {current_section}")
                continue
        
        # Parse based on current section
        if current_section == 'experience':
            try:
                if re.search(date_pattern, line) or (line_idx > 0 and not current_item and len(line) < 80):
                    if current_item:
                        resume_data['experience'].append(current_item)
                        current_item = {}
                    current_item['title'] = line.strip()
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        current_item['dates'] = date_match.group(0)
                        company_part = line[:date_match.start()].strip() if date_match.start() > 0 else ''
                        if company_part:
                            current_item['company'] = company_part
                            current_item['title'] = line[date_match.end():].strip() or 'Unknown Title'
                    else:
                        current_item['dates'] = ''
                    logger.debug(f"Experience item started: {current_item}")
                elif current_item and 'title' in current_item and not current_item.get('company'):
                    current_item['company'] = line.strip()
                    logger.debug(f"Added company to experience: {current_item['company']}")
                elif current_item:
                    current_item.setdefault('description', []).append(line.strip())
                    logger.debug(f"Added description to experience: {line}")
            except Exception as e:
                logger.warning(f"Skipping experience entry: {str(e)}")
                current_item = {}
        
        elif current_section == 'education':
            try:
                if re.search(date_pattern, line) or 'university' in line_lower or 'college' in line_lower or 'school' in line_lower:
                    if current_item:
                        resume_data['education'].append(current_item)
                        current_item = {}
                    current_item['institution'] = line.strip()
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        current_item['dates'] = date_match.group(0)
                        current_item['institution'] = line[:date_match.start()].strip() or 'Unknown Institution'
                    logger.debug(f"Education item started: {current_item}")
                elif current_item and not current_item.get('degree'):
                    if any(keyword in line_lower for keyword in ['bachelor', 'master', 'phd', 'diploma', 'b.sc', 'm.sc', 'b.tech', 'm.tech']):
                        current_item['degree'] = line.strip()
                        logger.debug(f"Added degree: {current_item['degree']}")
                    elif 'major' in line_lower or 'specialization' in line_lower:
                        current_item['major'] = line.strip()
                        logger.debug(f"Added major: {current_item['major']}")
                elif current_item:
                    gpa_match = re.search(gpa_pattern, line)
                    if gpa_match:
                        current_item['gpa'] = gpa_match.group(1)
                        logger.debug(f"Added GPA: {current_item['gpa']}")
                    else:
                        current_item.setdefault('details', []).append(line.strip())
                        logger.debug(f"Added education detail: {line}")
            except Exception as e:
                logger.warning(f"Skipping education entry: {str(e)}")
                current_item = {}
        
        elif current_section == 'skills':
            # Skills are often comma-separated or bulleted
            if ',' in line or line.startswith(('-', '•', '*')):
                skills = [s.strip() for s in line.replace('•', ',').replace('-', ',').replace('*', ',').split(',') if s.strip()]
                resume_data['skills'].extend(skills)
                logger.debug(f"Added skills: {skills}")
            else:
                resume_data['skills'].append(line.strip())
                logger.debug(f"Added skill: {line}")
        
        elif current_section == 'projects':
            try:
                if re.search(date_pattern, line) or len(line) < 80:
                    if current_item:
                        resume_data['projects'].append(current_item)
                        current_item = {}
                    current_item['title'] = line.strip()
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        current_item['date'] = date_match.group(0)
                        current_item['title'] = line[:date_match.start()].strip() or 'Unknown Project'
                    logger.debug(f"Project item started: {current_item}")
                elif current_item:
                    current_item.setdefault('description', []).append(line.strip())
                    logger.debug(f"Added project description: {line}")
            except Exception as e:
                logger.warning(f"Skipping project entry: {str(e)}")
                current_item = {}
        
        elif current_section == 'certifications':
            try:
                if re.search(date_pattern, line) or 'issued by' in line_lower or len(line) < 100:
                    if current_item:
                        resume_data['certifications'].append(current_item)
                        current_item = {}
                    current_item['name'] = line.strip()
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        current_item['date'] = date_match.group(0)
                        current_item['name'] = line[:date_match.start()].strip() or 'Unknown Certification'
                    logger.debug(f"Certification item started: {current_item}")
                elif current_item and 'issued by' in line_lower:
                    current_item['issuer'] = line.strip()
                    logger.debug(f"Added issuer: {current_item['issuer']}")
                elif current_item:
                    current_item['description'] = line.strip()
                    logger.debug(f"Added certification description: {line}")
            except Exception as e:
                logger.warning(f"Skipping certification entry: {str(e)}")
                current_item = {}
        
        elif current_section == 'publications':
            try:
                if re.search(date_pattern, line) or 'journal' in line_lower or 'conference' in line_lower:
                    if current_item:
                        resume_data['publications'].append(current_item)
                        current_item = {}
                    current_item['title'] = line.strip()
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        current_item['date'] = date_match.group(0)
                        current_item['title'] = line[:date_match.start()].strip() or 'Unknown Publication'
                    logger.debug(f"Publication item started: {current_item}")
                elif current_item and ('journal' in line_lower or 'conference' in line_lower):
                    current_item['journal'] = line.strip()
                    logger.debug(f"Added journal: {current_item['journal']}")
                elif current_item and 'author' in line_lower:
                    current_item['authors'] = line.strip()
                    logger.debug(f"Added authors: {current_item['authors']}")
                elif current_item:
                    current_item['description'] = line.strip()
                    logger.debug(f"Added publication description: {line}")
            except Exception as e:
                logger.warning(f"Skipping publication entry: {str(e)}")
                current_item = {}
        
        elif current_section == 'patents':
            try:
                if re.search(date_pattern, line) or 'patent no' in line_lower or len(line) < 100:
                    if current_item:
                        resume_data['patents'].append(current_item)
                        current_item = {}
                    current_item['title'] = line.strip()
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        current_item['date'] = date_match.group(0)
                        current_item['title'] = line[:date_match.start()].strip() or 'Unknown Patent'
                    logger.debug(f"Patent item started: {current_item}")
                elif current_item and 'patent no' in line_lower:
                    current_item['patent_number'] = line.strip()
                    logger.debug(f"Added patent number: {current_item['patent_number']}")
                elif current_item:
                    current_item['description'] = line.strip()
                    logger.debug(f"Added patent description: {line}")
            except Exception as e:
                logger.warning(f"Skipping patent entry: {str(e)}")
                current_item = {}
        
        elif current_section == 'workshops':
            try:
                if re.search(date_pattern, line) or 'organized by' in line_lower or len(line) < 100:
                    if current_item:
                        resume_data['workshops'].append(current_item)
                        current_item = {}
                    current_item['name'] = line.strip()
                    date_match = re.search(date_pattern, line)
                    if date_match:
                        current_item['date'] = date_match.group(0)
                        current_item['name'] = line[:date_match.start()].strip() or 'Unknown Workshop'
                    logger.debug(f"Workshop item started: {current_item}")
                elif current_item and 'organized by' in line_lower:
                    current_item['organizer'] = line.strip()
                    logger.debug(f"Added organizer: {current_item['organizer']}")
                elif current_item:
                    current_item['description'] = line.strip()
                    logger.debug(f"Added workshop description: {line}")
            except Exception as e:
                logger.warning(f"Skipping workshop entry: {str(e)}")
                current_item = {}
        
        elif current_section == 'languages':
            try:
                if ':' in line or '-' in line or 'proficient' in line_lower or 'fluent' in line_lower:
                    lang_parts = re.split(r'[:\-]', line, 1)
                    if len(lang_parts) == 2:
                        resume_data['languages'].append({
                            'language': lang_parts[0].strip(),
                            'proficiency': lang_parts[1].strip()
                        })
                        logger.debug(f"Added language: {lang_parts[0]} - {lang_parts[1]}")
                    else:
                        resume_data['languages'].append({
                            'language': line.strip(),
                            'proficiency': 'Not specified'
                        })
                        logger.debug(f"Added language: {line} - Not specified")
            except Exception as e:
                logger.warning(f"Skipping language entry: {str(e)}")
        
        elif current_section == 'professional_memberships':
            try:
                if len(line) < 100:
                    current_item = {'organization': line.strip()}
                    if 'role' in line_lower or 'member' in line_lower:
                        parts = re.split(r'[-,]', line, 1)
                        if len(parts) > 1:
                            current_item['organization'] = parts[0].strip()
                            current_item['role'] = parts[1].strip()
                    resume_data['professional_memberships'].append(current_item)
                    logger.debug(f"Added membership: {current_item}")
                    current_item = {}
            except Exception as e:
                logger.warning(f"Skipping membership entry: {str(e)}")
        
    # Save last item if exists
    if current_item and current_section and current_section != 'skills' and current_section != 'languages' and current_section != 'professional_memberships':
        resume_data[current_section].append(current_item)
        logger.debug(f"Saved final item for {current_section}: {current_item}")
    
    # Clean up skills (remove duplicates)
    resume_data['skills'] = list(set(resume_data['skills']))
    
    logger.info(f"Final resume_data.contact_info: {resume_data['contact_info']}")
    logger.info(f"Parsed resume_data: {resume_data}")
    return resume_data

def add_item_to_section(resume_data, section, item):
    """Add current item to appropriate section with proper formatting"""
    if not item:
        return
        
    if section in resume_data:
        resume_data[section].append(item)
    else:
        logger.warning(f"Unknown section: {section}")

def cleanup_resume_data(resume_data):
    """Clean up extracted resume data"""
    # Deduplicate skills
    if resume_data['skills']:
        # Normalize skill names
        normalized_skills = []
        seen_skills = set()
        for skill in resume_data['skills']:
            norm_skill = re.sub(r'[^\w\s]', '', skill.lower()).strip()
            if norm_skill and norm_skill not in seen_skills and len(norm_skill) > 1:
                seen_skills.add(norm_skill)
                normalized_skills.append(skill.strip())
        resume_data['skills'] = normalized_skills
    
    # Format experience descriptions as bullet points
    for exp in resume_data['experience']:
        if 'description' in exp and isinstance(exp['description'], list):
            # Filter out lines that are too short or appear to be dates
            exp['description'] = [line for line in exp['description'] 
                                if len(line) > 5 and not re.match(r'^[A-Za-z]+\s+\d{4}$', line.strip())]
                                
    # Clean up projects
    for proj in resume_data['projects']:
        if 'description' in proj and isinstance(proj['description'], list):
            proj['description'] = [line for line in proj['description'] if len(line) > 5]
            
    # Remove empty sections
    for section in list(resume_data.keys()):
        if section != 'contact_info' and not resume_data[section]:
            del resume_data[section]

def generate_resume_analysis(text, resume_data, career_field):
    """Generate AI analysis of the resume"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        You are an expert resume analyst specializing in {career_field}. Analyze the following resume text and provide professional feedback:
        
        Resume text:
        {text}
        
        Provide the following analysis in JSON format:
        1. "overall_impression": A brief overall assessment (30-50 words)
        2. "strengths": List 3 key strengths of this resume 
        3. "weaknesses": List 3 areas for improvement
        4. "ats_compatibility": Rate from 1-10 how well this would pass ATS systems with brief explanation
        5. "career_level": Determine the career level (Entry, Mid, Senior)
        6. "top_skills": List the 5 most marketable skills detected for {career_field}
        7. "industry_fit": Suggest 3 industries where this person would be a good fit
        8. "action_items": Provide 3 specific, actionable improvements
        9. "field_alignment": Rate from 1-10 how well the resume aligns with {career_field} requirements
        
        Include only the JSON in your response, no other text.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response to ensure valid JSON
        if response_text.startswith('```json'):
            response_text = response_text[7:].strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()
        
        try:
            analysis = json.loads(response_text)
        except json.JSONDecodeError:
            # Attempt to clean up the response
            response_text = re.sub(r'```.*?```', '', response_text, flags=re.DOTALL)
            response_text = response_text.replace("'", '"').replace('\n', ' ')
            # Try parsing again
            try:
                analysis = json.loads(response_text)
            except:
                # Fallback to default analysis
                analysis = default_analysis(resume_data, career_field)
        
        return analysis
        
    except Exception as e:
        logger.error(f"AI analysis error: {str(e)}")
        return default_analysis(resume_data, career_field)

def default_analysis(resume_data, career_field):
    """Fallback analysis when AI fails"""
    # Basic analysis based on parsed data
    strengths = []
    weaknesses = []
    
    # Check for skills
    if len(resume_data['skills']) > 5:
        strengths.append("Good range of technical skills")
    else:
        weaknesses.append("Limited skill set presented")
    
    # Check experience
    if len(resume_data['experience']) > 2:
        strengths.append("Solid work experience")
    else:
        weaknesses.append("Limited work history")
    
    # Check education
    if resume_data['education']:
        strengths.append("Educational qualifications included")
    else:
        weaknesses.append("Missing or incomplete education section")
    
    # Check projects
    if len(resume_data.get('projects', [])) > 1:
        strengths.append("Project experience demonstrates practical skills")
    else:
        weaknesses.append("Consider adding relevant projects")
        
    # Fill in missing strengths/weaknesses if needed
    while len(strengths) < 3:
        strengths.append("Resume submitted for analysis")
    while len(weaknesses) < 3:
        weaknesses.append("Consider adding more detail")
    
    field_specific_skills = {
        "Software Engineering": ["programming", "software development", "algorithms", "data structures"],
        "Mechanical Engineering": ["CAD", "thermodynamics", "fluid mechanics", "material science"],
        "Civil Engineering": ["structural analysis", "construction", "AutoCAD", "project planning"],
        "Electrical Engineering": ["circuit design", "power systems", "control systems", "PCB layout"],
        "Electronics & Communication": ["signal processing", "embedded systems", "communication protocols"],
        "Chemical Engineering": ["process design", "thermodynamics", "fluid dynamics", "reaction kinetics"],
        "Business & Management": ["leadership", "strategy", "operations", "analytics"],
        "Healthcare & Medicine": ["patient care", "medical terminology", "clinical experience", "research"],
        "Arts & Design": ["design", "creativity", "visual communication", "portfolio"],
        "General": ["communication", "teamwork", "problem-solving", "organization"]
    }
    
    # Get skills for the field or default to General
    top_skills = field_specific_skills.get(career_field, field_specific_skills["General"])
    
    # Try to find matches in resume skills
    matched_skills = []
    if resume_data['skills']:
        resume_skills_lower = [s.lower() for s in resume_data['skills']]
        for skill in top_skills:
            for resume_skill in resume_skills_lower:
                if skill.lower() in resume_skill:
                    matched_skills.append(skill)
                    break
    
    if matched_skills:
        top_skills = matched_skills[:5]
    
    # Determine career level based on experience
    career_level = "Entry"
    total_experience_years = 0
    for exp in resume_data['experience']:
        if 'dates' in exp:
            years_match = re.search(r'(\d{4})\s*(?:-|–|to)\s*(?:Present|Current|Now|(\d{4}))', exp['dates'])
            if years_match:
                start_year = int(years_match.group(1))
                end_year = int(years_match.group(2)) if years_match.group(2) else datetime.now().year
                total_experience_years += (end_year - start_year)
    
    if total_experience_years > 8:
        career_level = "Senior"
    elif total_experience_years > 3:
        career_level = "Mid"
    
    return {
        "overall_impression": f"Basic resume with standard sections for {career_field}. Consider enhancing content with more specific achievements and metrics.",
        "strengths": strengths[:3],
        "weaknesses": weaknesses[:3],
        "ats_compatibility": 6,
        "career_level": career_level,
        "top_skills": top_skills,
        "industry_fit": get_industry_fit(career_field),
        "action_items": [
            "Add measurable achievements with specific metrics",
            "Ensure all experience includes start and end dates",
            f"Tailor skills section to match {career_field} job descriptions"
        ],
        "field_alignment": 7
    }

def get_industry_fit(career_field):
    """Get relevant industries based on career field"""
    industry_mapping = {
        "Software Engineering": ["Technology", "Finance", "Healthcare IT"],
        "Mechanical Engineering": ["Manufacturing", "Automotive", "Aerospace"],
        "Civil Engineering": ["Construction", "Infrastructure", "Urban Planning"],
        "Electrical Engineering": ["Energy", "Manufacturing", "Telecommunications"],
        "Electronics & Communication": ["Telecommunications", "Consumer Electronics", "Automation"],
        "Chemical Engineering": ["Pharmaceuticals", "Oil & Gas", "Materials Science"],
        "Business & Management": ["Consulting", "Finance", "Retail"],
        "Healthcare & Medicine": ["Healthcare", "Pharmaceuticals", "Medical Devices"],
        "Arts & Design": ["Media", "Advertising", "Entertainment"],
        "Education & Teaching": ["Education", "EdTech", "Training & Development"],
        "Finance & Accounting": ["Banking", "Financial Services", "Consulting"],
        "Legal": ["Law Firms", "Corporate Legal", "Legal Services"],
        "Marketing & Sales": ["Advertising", "Retail", "Consumer Goods"],
        "Human Resources": ["HR Services", "Recruiting", "Corporate Services"],
        "Research & Science": ["R&D", "Pharmaceuticals", "Academia"],
        "General": ["Business Services", "Technology", "Consulting"]
    }
    
    return industry_mapping.get(career_field, ["Technology", "Business", "Consulting"])

def generate_skill_match(text, job_title, industry, career_field):
    """Generate skill match analysis for a specific job title"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        You are an AI resume expert that specializes in skill matching for {career_field} professionals. 
        
        Job Title: {job_title}
        Industry: {industry}
        Career Field: {career_field}
        
        Resume Text:
        {text}
        
        Analyze the resume and provide the following in JSON format:
        1. "key_skills_for_role": List 8 important skills for this job title in this field
        2. "matching_skills": Skills in the resume that match the job requirements
        3. "missing_skills": Important skills for this role that are missing from the resume
        4. "match_percentage": An integer from 0-100 representing the overall match
        5. "improvement_suggestions": 3 specific suggestions to better target this role
        6. "technical_skill_match": Assessment of technical skills match (excellent/good/fair/poor)
        7. "soft_skill_match": Assessment of soft skills match (excellent/good/fair/poor)
        8. "industry_knowledge": Assessment of industry/domain knowledge (excellent/good/fair/poor)
        
        Include only the JSON in your response.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response
        if response_text.startswith('```json'):
            response_text = response_text[7:].strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()
        
        try:
            match_data = json.loads(response_text)
            return match_data
        except:
            # Return default match data
            return default_skill_match(job_title, career_field)
    except Exception as e:
        logger.error(f"Skill match error: {str(e)}")
        return default_skill_match(job_title, career_field)

def default_skill_match(job_title, career_field):
    """Fallback skill match when AI fails"""
    field_skills = {
        "Software Engineering": ["Programming", "Software Development", "Algorithms", "Data Structures", 
                               "Version Control", "Testing", "Debugging", "Documentation"],
        "Mechanical Engineering": ["CAD", "Thermal Analysis", "Fluid Mechanics", "Material Science", 
                                 "Manufacturing Processes", "Stress Analysis", "Prototyping", "GD&T"],
        "Civil Engineering": ["Structural Analysis", "Construction Management", "AutoCAD", "Surveying", 
                            "Environmental Engineering", "Soil Mechanics", "Hydrology", "Urban Planning"],
        "Electrical Engineering": ["Circuit Design", "Power Systems", "Control Systems", "Instrumentation", 
                                "Electrical Safety", "PCB Layout", "Signal Processing", "Automation"],
        "Electronics & Communication": ["Signal Processing", "Embedded Systems", "Communication Protocols", 
                                      "Network Design", "RF Design", "Wireless", "Digital Logic", "Testing"],
        "General": ["Project Management", "Communication", "Team Leadership", "Problem-solving", 
                  "Time Management", "Technical Writing", "Presentations", "Data Analysis"]
    }
    
    # Get skills for the field or default to General
    key_skills = field_skills.get(career_field, field_skills["General"])
    
    return {
        "key_skills_for_role": key_skills,
        "matching_skills": ["Some skills may match - detailed analysis unavailable"],
        "missing_skills": ["Consider researching specific skills for this role"],
        "match_percentage": 50,
        "improvement_suggestions": [
            f"Research key qualifications for {job_title} roles",
            "Add metrics and achievements to demonstrate impact",
            f"Highlight specific {career_field} projects that demonstrate required skills"
        ],
        "technical_skill_match": "fair",
        "soft_skill_match": "fair",
        "industry_knowledge": "fair"
    }

def calculate_resume_stats(resume_data, career_field):
    """Calculate statistics from resume data"""
    stats = {}
    
    # Calculate experience years
    total_experience = 0
    for exp in resume_data['experience']:
        if 'dates' in exp:
            # Try to extract years
            years_match = re.search(r'(\d{4})\s*(?:-|–|to)\s*(?:Present|Current|Now|(\d{4}))', exp['dates'])
            if years_match:
                start_year = int(years_match.group(1))
                end_year = int(years_match.group(2)) if years_match.group(2) else datetime.now().year
                total_experience += (end_year - start_year)
    
    stats['years_experience'] = total_experience
    
    # Skill count
    stats['skill_count'] = len(resume_data['skills'])
    
    # Education level
    education_level = "None"
    for edu in resume_data['education']:
        edu_text = json.dumps(edu).lower()
        if 'phd' in edu_text or 'doctorate' in edu_text:
            education_level = "PhD"
            break
        elif 'master' in edu_text or 'ms' in edu_text or 'ma' in edu_text or 'mba' in edu_text:
            education_level = "Master's"
        elif 'bachelor' in edu_text or 'bs' in edu_text or 'ba' in edu_text and education_level != "Master's":
            education_level = "Bachelor's"
    
    stats['education_level'] = education_level
    stats['project_count'] = len(resume_data.get('projects', []))
    stats['cert_count'] = len(resume_data.get('certifications', []))
    stats['publication_count'] = len(resume_data.get('publications', []))
    stats['patent_count'] = len(resume_data.get('patents', []))
    stats['language_count'] = len(resume_data.get('languages', []))
    
    # Field-specific skills categorization
    field_skill_categories = {
        "Software Engineering": {
            'programming': ['python', 'java', 'c++', 'javascript', 'html', 'css', 'php', 'ruby', 'golang', 'swift'],
            'frameworks': ['react', 'angular', 'vue', 'django', 'flask', 'spring', '.net', 'laravel', 'express'],
            'databases': ['sql', 'mysql', 'mongodb', 'postgresql', 'oracle', 'redis', 'cassandra', 'dynamodb'],
            'devops': ['docker', 'kubernetes', 'jenkins', 'git', 'aws', 'azure', 'gcp', 'terraform', 'ci/cd'],
            'general_tech': ['algorithms', 'data structures', 'api', 'microservices', 'testing', 'agile', 'scrum']
        },
        "Mechanical Engineering": {
            'design': ['cad', 'solidworks', 'autocad', 'creo', 'catia', 'nx', 'fusion', 'inventor', 'drafting'],
            'analysis': ['fea', 'ansys', 'abaqus', 'cfd', 'thermal', 'simulation', 'nastran', 'stress analysis'],
            'manufacturing': ['cnc', 'gd&t', 'machining', 'welding', 'additive manufacturing', '3d printing'],
            'technical': ['thermodynamics', 'fluid mechanics', 'heat transfer', 'dynamics', 'materials', 'vibration'],
            'general_eng': ['project management', 'design review', 'testing', 'prototyping', 'quality control']
        },
        "Civil Engineering": {
            'design': ['autocad', 'revit', 'civil 3d', 'microstation', 'sketchup', 'structural design'],
            'analysis': ['structural analysis', 'sap', 'etabs', 'staad', 'robot', 'foundation design'],
            'construction': ['construction management', 'scheduling', 'estimating', 'cost control', 'site supervision'],
            'technical': ['hydrology', 'hydraulics', 'geotechnical', 'transportation', 'environmental', 'surveying'],
            'general_eng': ['building codes', 'permitting', 'specifications', 'quality control', 'sustainability']
        },
        "Electrical Engineering": {
            'design': ['circuit design', 'pcb', 'schematic', 'cad', 'altium', 'eagle', 'kicad', 'cadence'],
            'power': ['power systems', 'power electronics', 'motor control', 'transformers', 'distribution'],
            'control': ['plc', 'scada', 'automation', 'instrumentation', 'control systems', 'hmi'],
            'technical': ['analog', 'digital', 'embedded', 'microcontroller', 'fpga', 'signal processing'],
            'general_eng': ['circuit analysis', 'troubleshooting', 'prototyping', 'testing', 'documentation']
        },
        "General": {
            'soft_skills': ['communication', 'leadership', 'teamwork', 'problem solving', 'critical thinking'],
            'management': ['project management', 'team management', 'budget', 'planning', 'strategy'],
            'analysis': ['data analysis', 'research', 'reporting', 'documentation', 'quality assurance'],
            'tools': ['excel', 'word', 'powerpoint', 'outlook', 'crm', 'erp', 'office'],
            'general': ['time management', 'organization', 'customer service', 'presentation', 'writing']
        }
    }
    
    # Use General as fallback
    skill_categories = field_skill_categories.get(career_field, field_skill_categories["General"])
    
    # Calculate skill distribution
    skill_text = ' '.join(resume_data['skills']).lower()
    skill_distribution = {}
    
    for category, keywords in skill_categories.items():
        count = sum(1 for keyword in keywords if keyword in skill_text)
        skill_distribution[category] = count
    
    stats['skill_distribution'] = skill_distribution
    
    # Additional stats - experience recency (years since most recent job)
    most_recent_year = 0
    for exp in resume_data['experience']:
        if 'dates' in exp:
            # Find the most recent year mentioned
            years = re.findall(r'\b(20\d{2}|19\d{2})\b', exp['dates'])
            if years:
                year = max(int(y) for y in years)
                most_recent_year = max(most_recent_year, year)
    
    if most_recent_year:
        stats['years_since_last_job'] = max(0, datetime.now().year - most_recent_year)
    else:
        stats['years_since_last_job'] = 0
        
    # Calculate average job tenure
    job_durations = []
    for exp in resume_data['experience']:
        if 'dates' in exp:
            years_match = re.search(r'(\d{4})\s*(?:-|–|to)\s*(?:Present|Current|Now|(\d{4}))', exp['dates'])
            if years_match:
                start_year = int(years_match.group(1))
                end_year = int(years_match.group(2)) if years_match.group(2) else datetime.now().year
                duration = end_year - start_year
                if 0 < duration < 20:  # Filter out likely parsing errors
                    job_durations.append(duration)
    
    stats['avg_job_tenure'] = round(sum(job_durations) / len(job_durations), 1) if job_durations else 0
    
    return stats

def generate_resume_charts(stats):
    """Generate visualization for resume stats"""
    try:
        plt.figure(figsize=(12, 9))
        
        # Create a 2x2 subplot
        plt.subplot(2, 2, 1)
        # Create education and experience chart
        labels = ['Experience (years)', 'Projects', 'Certifications']
        values = [stats['years_experience'], stats.get('project_count', 0), stats.get('cert_count', 0)]
        plt.bar(['Experience', 'Projects', 'Certifications'], values, color=['#4285F4', '#34A853', '#FBBC05'])
        plt.title('Experience & Credentials')
        
        # Create skill distribution chart
        plt.subplot(2, 2, 2)
        if 'skill_distribution' in stats:
            categories = list(stats['skill_distribution'].keys())
            counts = list(stats['skill_distribution'].values())
            plt.bar(categories, counts, color=['#4285F4', '#34A853', '#FBBC05', '#EA4335', '#5F6368'])
            plt.title('Skill Distribution')
            plt.xticks(rotation=45, ha='right')
        else:
            plt.text(0.5, 0.5, 'No skill distribution data', horizontalalignment='center', verticalalignment='center')
            plt.title('Skill Distribution')
        
        # Create education level pie chart
        plt.subplot(2, 2, 3)
        education_level = stats.get('education_level', 'None')
        education_values = {
            'PhD': 3,
            'Master\'s': 2,
            'Bachelor\'s': 1,
            'None': 0
        }
        
        edu_labels = ['PhD', 'Master\'s', 'Bachelor\'s', 'Other']
        edu_values = [0, 0, 0, 0]
        
        if education_level == 'PhD':
            edu_values = [1, 0, 0, 0]
        elif education_level == 'Master\'s':
            edu_values = [0, 1, 0, 0]
        elif education_level == 'Bachelor\'s':
            edu_values = [0, 0, 1, 0]
        else:
            edu_values = [0, 0, 0, 1]
            
        plt.pie(edu_values, labels=edu_labels, autopct=lambda p: f'{p:.1f}%' if p > 0 else '', 
                colors=['#4285F4', '#34A853', '#FBBC05', '#EA4335'])
        plt.title('Education Level')
        
        # Create additional stats
        plt.subplot(2, 2, 4)
        add_stats = [
            stats.get('skill_count', 0),
            stats.get('publication_count', 0) + stats.get('patent_count', 0),
            stats.get('language_count', 0)
        ]
        plt.bar(['Skills', 'Publications\n& Patents', 'Languages'], add_stats, color=['#4285F4', '#34A853', '#FBBC05'])
        plt.title('Additional Credentials')
        
        plt.tight_layout()
        
        # Save plot to a base64 string
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        plt.close()
        
        return f"data:image/png;base64,{image_base64}"
        
    except Exception as e:
        logger.error(f"Chart generation error: {str(e)}")
        return ""

def generate_field_recommendations(text, resume_data, career_field):
    """Generate field-specific recommendations"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        You're a career coach specializing in {career_field}. Review this resume text and provide specific recommendations.
        
        Resume text:
        {text}
        
        Provide field-specific recommendations in JSON format:
        1. "industry_trends": 3 current trends in {career_field} the candidate should highlight
        2. "key_certifications": 3 valuable certifications for {career_field} professionals
        3. "technical_skills": 3 technical skills to develop for career advancement
        4. "resume_format": Specific formatting advice for {career_field} resumes
        5. "portfolio_tips": How to showcase {career_field} work effectively
        
        Return only the JSON output.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response
        if response_text.startswith('```json'):
            response_text = response_text[7:].strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()
        
        try:
            recommendations = json.loads(response_text)
            return recommendations
        except:
            # Return default recommendations
            return default_field_recommendations(career_field)
    except Exception as e:
        logger.error(f"Field recommendations error: {str(e)}")
        return default_field_recommendations(career_field)

def default_field_recommendations(career_field):
    """Default field-specific recommendations when AI fails"""
    field_recommendations = {
        "Software Engineering": {
            "industry_trends": [
                "Cloud-native development and containerization",
                "Machine learning and AI integration",
                "DevOps and continuous deployment practices"
            ],
            "key_certifications": [
                "AWS or Azure cloud certifications",
                "Professional Scrum certifications",
                "Specialized framework certifications (React, Spring, etc.)"
            ],
            "technical_skills": [
                "Containerization and orchestration (Docker, Kubernetes)",
                "CI/CD pipeline implementation",
                "Cloud architecture design patterns"
            ],
            "resume_format": "Highlight specific technologies, languages, and frameworks. Include GitHub and project links. Quantify impact with metrics.",
            "portfolio_tips": "Maintain an active GitHub profile with clean, documented projects. Include README files and deployment instructions."
        },
        "Mechanical Engineering": {
            "industry_trends": [
                "Digital twin technology and simulation",
                "Additive manufacturing (3D printing) techniques",
                "Sustainability and green engineering practices"
            ],
            "key_certifications": [
                "Certified SolidWorks Professional (CSWP)",
                "FE/PE certification",
                "Six Sigma certification"
            ],
            "technical_skills": [
                "Modern CAD software proficiency",
                "FEA and simulation expertise",
                "GD&T implementation"
            ],
            "resume_format": "Emphasize specific design projects, CAD packages, and manufacturing processes. Include metrics on cost reduction or process improvement.",
            "portfolio_tips": "Create a portfolio with 3D models, design iterations, and final products. Include FEA results and optimization processes."
        },
        "Civil Engineering": {
            "industry_trends": [
                "BIM (Building Information Modeling) implementation",
                "Sustainable infrastructure development",
                "Resilient design for climate change"
            ],
            "key_certifications": [
                "PE license",
                "LEED certification",
                "PMP certification"
            ],
            "technical_skills": [
                "Advanced BIM software proficiency",
                "Sustainable design principles",
                "Modern structural analysis software"
            ],
            "resume_format": "Highlight specific infrastructure projects, design codes used, and construction oversight experience. Quantify project scales and budgets.",
            "portfolio_tips": "Include project renderings, construction photos, and before/after comparisons. Document problem-solving approaches for site challenges."
        },
        "General": {
            "industry_trends": [
                "Digital transformation across industries",
                "Data-driven decision making",
                "Remote collaboration tools and techniques"
            ],
            "key_certifications": [
                "Project Management Professional (PMP)",
                "Industry-specific certifications",
                "Leadership development certifications"
            ],
            "technical_skills": [
                "Data analysis and visualization",
                "Digital collaboration tools",
                "Industry-specific software"
            ],
            "resume_format": "Balance technical skills with leadership and soft skills. Quantify achievements with specific metrics. Use industry terminology.",
            "portfolio_tips": "Create a professional portfolio showcasing key projects, presentations, and achievements. Include testimonials if possible."
        }
    }
    
    return field_recommendations.get(career_field, field_recommendations["General"])

def analyze_resume_keywords(text, career_field):
    """Analyze keyword density and ATS relevance"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        You are an ATS optimization expert for {career_field} resumes. Analyze this resume text for keyword effectiveness.
        
        Resume text:
        {text}
        
        Provide the following in JSON format:
        1. "top_keywords": List the 10 most frequently used professional keywords
        2. "missing_keywords": 5 important keywords for {career_field} that should be added
        3. "keyword_density": Overall assessment of keyword usage (low/medium/high)
        4. "ats_tips": 3 specific tips to improve ATS compatibility
        
        Return only the JSON output.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response
        if response_text.startswith('```json'):
            response_text = response_text[7:].strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()
        
        try:
            keyword_analysis = json.loads(response_text)
            return keyword_analysis
        except:
            # Return default analysis
            return default_keyword_analysis(career_field)
    except Exception as e:
        logger.error(f"Keyword analysis error: {str(e)}")
        return default_keyword_analysis(career_field)

def default_keyword_analysis(career_field):
    """Default keyword analysis when AI fails"""
    field_keywords = {
        "Software Engineering": {
            "top_keywords": ["software", "development", "programming", "coding", "engineering", 
                          "application", "design", "testing", "implementation", "algorithm"],
            "missing_keywords": ["agile", "CI/CD", "cloud native", "microservices", "test-driven development"]
        },
        "Mechanical Engineering": {
            "top_keywords": ["mechanical", "design", "engineering", "manufacturing", "CAD", 
                          "analysis", "project", "testing", "development", "technical"],
            "missing_keywords": ["GD&T", "thermal analysis", "tolerance", "six sigma", "quality control"]
        },
        "Civil Engineering": {
            "top_keywords": ["civil", "structural", "design", "engineering", "construction", 
                          "project", "site", "analysis", "management", "development"],
            "missing_keywords": ["BIM", "LEED", "permitting", "specifications", "building codes"]
        },
        "Electrical Engineering": {
            "top_keywords": ["electrical", "design", "engineering", "power", "circuit", 
                          "control", "systems", "testing", "project", "development"],
            "missing_keywords": ["PLC", "SCADA", "instrumentation", "schematics", "troubleshooting"]
        },
        "General": {
            "top_keywords": ["experience", "project", "management", "development", "skills", 
                          "team", "analysis", "technical", "professional", "leadership"],
            "missing_keywords": ["strategic", "data-driven", "collaboration", "innovation", "implementation"]
        }
    }
    
    keywords = field_keywords.get(career_field, field_keywords["General"])
    
    return {
        "top_keywords": keywords["top_keywords"],
        "missing_keywords": keywords["missing_keywords"],
        "keyword_density": "medium",
        "ats_tips": [
            "Use specific job titles that match target positions",
            "Include both spelled-out terms and acronyms (e.g., 'Project Management Professional (PMP)')",
            "Place important keywords in section headings and job titles for greater weight"
        ]
    }

def check_international_compatibility(text, resume_data):
    """Check resume for international job application compatibility"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        As an international resume expert, evaluate this resume for global job applications.
        
        Resume text:
        {text}
        
        Provide the following in JSON format:
        1. "global_compatibility": Rate from 1-10 how well this resume works internationally
        2. "us_compatibility": US-specific assessment (good/needs work)
        3. "europe_compatibility": Europe-specific assessment (good/needs work)
        4. "asia_compatibility": Asia-specific assessment (good/needs work)
        5. "recommendations": 3 specific changes to improve international compatibility
        
        Return only the JSON output.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response
        if response_text.startswith('```json'):
            response_text = response_text[7:].strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()
        
        try:
            compatibility = json.loads(response_text)
            return compatibility
        except:
            # Return default compatibility assessment
            return {
                "global_compatibility": 6,
                "us_compatibility": "needs work",
                "europe_compatibility": "needs work",
                "asia_compatibility": "needs work",
                "recommendations": [
                    "Include a professional summary tailored to global audiences",
                    "Add an International section with language proficiencies and global experience",
                    "Ensure dates and education credentials follow international formats"
                ]
            }
    except Exception as e:
        logger.error(f"International compatibility check error: {str(e)}")
        return {
            "global_compatibility": 5,
            "us_compatibility": "needs work",
            "europe_compatibility": "needs work",
            "asia_compatibility": "needs work",
            "recommendations": [
                "Add an International section with relevant information",
                "Format dates in an internationally recognized format (DD/MM/YYYY)",
                "Include language proficiencies and cultural adaptability"
                        ]
        }

def assess_personality_traits(text):
    """Assess personality traits based on resume content"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = f"""
        You are a career psychologist analyzing a resume to infer personality traits based on the language, achievements, and content structure.
        
        Resume text:
        {text}
        
        Provide the following in JSON format:
        1. "leadership": Assessment of leadership traits (strong/moderate/weak) with brief evidence
        2. "teamwork": Assessment of collaboration traits (strong/moderate/weak) with brief evidence
        3. "initiative": Assessment of proactiveness (strong/moderate/weak) with brief evidence
        4. "adaptability": Assessment of flexibility (strong/moderate/weak) with brief evidence
        5. "attention_to_detail": Assessment of precision (strong/moderate/weak) with brief evidence
        6. "recommendations": 3 suggestions to highlight positive traits more effectively
        
        Return only the JSON output.
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up response
        if response_text.startswith('```json'):
            response_text = response_text[7:].strip()
        if response_text.endswith('```'):
            response_text = response_text[:-3].strip()
        
        try:
            personality = json.loads(response_text)
            return personality
        except:
            # Return default personality assessment
            return default_personality_assessment(text)
    except Exception as e:
        logger.error(f"Personality assessment error: {str(e)}")
        return default_personality_assessment(text)

def default_personality_assessment(text):
    """Default personality assessment when AI fails"""
    # Basic analysis based on text patterns
    leadership_score = "weak"
    teamwork_score = "weak"
    initiative_score = "weak"
    adaptability_score = "weak"
    detail_score = "weak"
    
    text_lower = text.lower()
    
    # Leadership indicators
    if any(keyword in text_lower for keyword in ['led ', 'managed ', 'supervised ', 'directed ', 'oversaw ', 'executive']):
        leadership_score = "strong"
    elif any(keyword in text_lower for keyword in ['team lead', 'project manager', 'coordinated']):
        leadership_score = "moderate"
        
    # Teamwork indicators
    if any(keyword in text_lower for keyword in ['collaborated ', 'team ', 'worked with ', 'group ', 'partnership']):
        teamwork_score = "strong"
    elif 'team' in text_lower:
        teamwork_score = "moderate"
        
    # Initiative indicators
    if any(keyword in text_lower for keyword in ['initiated ', 'developed ', 'proposed ', 'launched ', 'created ', 'innovated']):
        initiative_score = "strong"
    elif any(keyword in text_lower for keyword in ['improved ', 'enhanced ', 'contributed']):
        initiative_score = "moderate"
        
    # Adaptability indicators
    if any(keyword in text_lower for keyword in ['adapted ', 'flexible ', 'pivot ', 'adjusted ', 'multiple roles']):
        adaptability_score = "strong"
    elif any(keyword in text_lower for keyword in ['various ', 'diverse ', 'multiple']):
        adaptability_score = "moderate"
        
    # Attention to detail indicators
    if any(keyword in text_lower for keyword in ['optimized ', 'streamlined ', 'accuracy ', 'meticulous ', 'detailed']):
        detail_score = "strong"
    elif any(keyword in text_lower for keyword in ['organized ', 'structured ', 'systematic']):
        detail_score = "moderate"
    
    return {
        "leadership": {
            "score": leadership_score,
            "evidence": "Based on general resume content analysis" if leadership_score == "weak" else f"Presence of leadership terms suggests {leadership_score} capability"
        },
        "teamwork": {
            "score": teamwork_score,
            "evidence": "Based on general resume content analysis" if teamwork_score == "weak" else f"Team-related terms indicate {teamwork_score} collaboration"
        },
        "initiative": {
            "score": initiative_score,
            "evidence": "Based on general resume content analysis" if initiative_score == "weak" else f"Initiative terms show {initiative_score} proactiveness"
        },
        "adaptability": {
            "score": adaptability_score,
            "evidence": "Based on general resume content analysis" if adaptability_score == "weak" else f"Flexibility terms suggest {adaptability_score} adaptability"
        },
        "attention_to_detail": {
            "score": detail_score,
            "evidence": "Based on general resume content analysis" if detail_score == "weak" else f"Detail-oriented terms indicate {detail_score} precision"
        },
        "recommendations": [
            "Use action verbs to highlight leadership and initiative (e.g., 'spearheaded', 'pioneered')",
            "Include specific examples of teamwork and collaboration in experience descriptions",
            "Quantify achievements to demonstrate attention to detail and impact"
        ]
    }

# Additional utility functions
def validate_upload_folder():
    """Ensure upload folder exists and is secure"""
    upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
    if not os.path.exists(upload_folder):
        try:
            os.makedirs(upload_folder)
            # Set secure permissions
            os.chmod(upload_folder, 0o700)
        except Exception as e:
            logger.error(f"Failed to create upload folder: {str(e)}")
            flash('Server error: Unable to process uploads.', 'error')
            return False
    return True

def sanitize_text(text):
    """Sanitize extracted text to prevent XSS and other issues"""
    # Remove any potential script tags or dangerous content
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'javascript:', '', text, flags=re.IGNORECASE)
    return text

# Configuration for upload folder and allowed file size
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB limit

# Ensure upload folder is set up on application start

def setup_upload_folder():
    validate_upload_folder()

# Error handling for file size limit
@app.errorhandler(413)
def request_entity_too_large(error):
    flash('File too large. Maximum size is 5MB.', 'error')
    return redirect(url_for('analyze_resume'))

# Helper function to initialize logging
def setup_logging():
    """Configure logging for the application"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('resume_analyzer.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

# Initialize logger
logger = setup_logging()    

@app.route('/admin/logged-in-users')
@admin_required
def admin_logged_in_users():
    return render_template('admin_logged_in_users.html', logged_in_users=logged_in_users)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        conn = sqlite3.connect('resume_builder.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM users WHERE is_admin = 1')
        admin_users = c.fetchone()[0]
        c.execute('SELECT full_name, created_at FROM users ORDER BY created_at DESC LIMIT 5')
        recent_users = c.fetchall()

        c.execute('SELECT COUNT(*) FROM contact_messages WHERE status = "pending"')
        pending_messages = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM contact_messages WHERE status = "in-progress"')
        in_progress_messages = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM contact_messages WHERE status = "completed"')
        completed_messages = c.fetchone()[0]

        c.execute('SELECT action, timestamp FROM activity_log ORDER BY timestamp DESC LIMIT 5')
        recent_activity = c.fetchall()

        conn.close()

        return render_template('admin_dashboard.html',
                             total_users=total_users,
                             admin_users=admin_users,
                             recent_users=recent_users,
                             pending_messages=pending_messages,
                             in_progress_messages=in_progress_messages,
                             completed_messages=completed_messages,
                             recent_activity=recent_activity)
    except Exception as e:
        logger.error(f"Error in admin_dashboard: {str(e)}")
        flash('An error occurred while loading the dashboard.', 'error')
        return redirect(url_for('index'))

@app.route('/admin/contacts')
@admin_required
def admin_contacts():
    try:
        conn = sqlite3.connect('resume_builder.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        status = request.args.get('status', '')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        
        valid_sort_columns = ['id', 'first_name', 'last_name', 'email', 'phone', 'message', 'status', 'created_at']
        if sort_by not in valid_sort_columns:
            sort_by = 'created_at'
        if sort_order not in ['asc', 'desc']:
            sort_order = 'desc'
        
        query = "SELECT * FROM contact_messages"
        params = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += f" ORDER BY {sort_by} {sort_order}"
        
        c.execute(query, params)
        messages = c.fetchall()
        
        conn.close()
        
        return render_template('admin_contacts.html', 
                             messages=messages, 
                             status_filter=status, 
                             sort_by=sort_by, 
                             sort_order=sort_order)
    except Exception as e:
        logger.error(f"Error in admin_contacts: {str(e)}")
        flash(f"An error occurred while retrieving contact messages: {str(e)}", 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/contacts/<int:message_id>/update', methods=['POST'])
@admin_required
def update_contact_status(message_id):
    try:
        status = request.form.get('status', '')
        if not status or status not in ['pending', 'in-progress', 'completed']:
            flash('Invalid status value.', 'error')
            return redirect(url_for('admin_contacts'))
            
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('UPDATE contact_messages SET status = ? WHERE id = ?', 
                 (status, message_id))
        c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                 (f"Updated message {message_id} status to {status}", session['user_id']))
        conn.commit()
        conn.close()
        
        flash('Contact message status updated successfully.', 'success')
        return redirect(url_for('admin_contacts'))
    except Exception as e:
        logger.error(f"Error in update_contact_status: {str(e)}")
        flash('An error occurred while updating the message status.', 'error')
        return redirect(url_for('admin_contacts'))

@app.route('/admin/contacts/<int:message_id>/delete', methods=['POST'])
@admin_required
def delete_contact(message_id):
    try:
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('DELETE FROM contact_messages WHERE id = ?', (message_id,))
        c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                 (f"Deleted message {message_id}", session['user_id']))
        conn.commit()
        conn.close()
        
        flash('Contact message deleted successfully.', 'success')
        return redirect(url_for('admin_contacts'))
    except Exception as e:
        logger.error(f"Error in delete_contact: {str(e)}")
        flash('An error occurred while deleting the message.', 'error')
        return redirect(url_for('admin_contacts'))

@app.route('/admin/contacts/bulk-delete', methods=['POST'])
@admin_required
def bulk_delete_contacts():
    try:
        message_ids = request.form.getlist('message_ids')
        if not message_ids:
            flash('No messages selected for deletion.', 'error')
            return redirect(url_for('admin_contacts'))
        
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.executemany('DELETE FROM contact_messages WHERE id = ?', [(int(mid),) for mid in message_ids])
        for mid in message_ids:
            c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                     (f"Deleted message {mid} (bulk)", session['user_id']))
        conn.commit()
        conn.close()
        
        flash(f'Successfully deleted {len(message_ids)} message(s).', 'success')
        return redirect(url_for('admin_contacts'))
    except Exception as e:
        logger.error(f"Error in bulk_delete_contacts: {str(e)}")
        flash('An error occurred while deleting messages.', 'error')
        return redirect(url_for('admin_contacts'))

@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        conn = sqlite3.connect('resume_builder.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT id, email, full_name, is_admin, created_at FROM users ORDER BY created_at DESC')
        users = c.fetchall()
        conn.close()
        return render_template('admin_users.html', users=users)
    except Exception as e:
        logger.error(f"Error in admin_users: {str(e)}")
        flash('An error occurred while retrieving users.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/users/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    try:
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('SELECT is_admin FROM users WHERE id = ?', (user_id,))
        current_status = c.fetchone()[0]
        new_status = 0 if current_status else 1
        c.execute('UPDATE users SET is_admin = ? WHERE id = ?', (new_status, user_id))
        c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                 (f"{'Made' if new_status else 'Removed'} user {user_id} as admin", session['user_id']))
        conn.commit()
        conn.close()
        flash(f'User admin status updated to {"Admin" if new_status else "Regular"}.', 'success')
        return redirect(url_for('admin_users'))
    except Exception as e:
        logger.error(f"Error in toggle_admin: {str(e)}")
        flash('An error occurred while updating user status.', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    try:
        if user_id == session['user_id']:
            flash('You cannot delete yourself.', 'error')
            return redirect(url_for('admin_users'))
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))
        c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                 (f"Deleted user {user_id}", session['user_id']))
        if user_id in logged_in_users:
            del logged_in_users[user_id]
        conn.commit()
        conn.close()
        flash('User deleted successfully.', 'success')
        return redirect(url_for('admin_users'))
    except Exception as e:
        logger.error(f"Error in delete_user: {str(e)}")
        flash('An error occurred while deleting the user.', 'error')
        return redirect(url_for('admin_users'))

@app.route('/admin/export/users')
@admin_required
def export_users():
    try:
        conn = sqlite3.connect('resume_builder.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT id, email, full_name, is_admin, created_at FROM users')
        users = c.fetchall()
        conn.close()

        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(['ID', 'Email', 'Full Name', 'Is Admin', 'Created At'])
        for user in users:
            writer.writerow([user['id'], user['email'], user['full_name'], user['is_admin'], user['created_at']])
        
        output = si.getvalue()
        si.close()
        return Response(output, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=users_export.csv"})
    except Exception as e:
        logger.error(f"Error in export_users: {str(e)}")
        flash('An error occurred while exporting users.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/export/messages')
@admin_required
def export_messages():
    try:
        conn = sqlite3.connect('resume_builder.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT id, first_name, last_name, email, phone, message, status, created_at FROM contact_messages')
        messages = c.fetchall()
        conn.close()

        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(['ID', 'First Name', 'Last Name', 'Email', 'Phone', 'Message', 'Status', 'Created At'])
        for msg in messages:
            writer.writerow([msg['id'], msg['first_name'], msg['last_name'], msg['email'], msg['phone'], msg['message'], msg['status'], msg['created_at']])
        
        output = si.getvalue()
        si.close()
        return Response(output, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=messages_export.csv"})
    except Exception as e:
        logger.error(f"Error in export_messages: {str(e)}")
        flash('An error occurred while exporting messages.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/profile', methods=['GET', 'POST'])
@admin_required
def admin_profile():
    if request.method == 'POST':
        new_name = request.form.get('full_name')
        if new_name:
            session['user_name'] = new_name
            if session['user_id'] != 0:
                conn = sqlite3.connect('resume_builder.db')
                c = conn.cursor()
                c.execute('UPDATE users SET full_name = ? WHERE id = ?', (new_name, session['user_id']))
                c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                         (f"Updated profile name to {new_name}", session['user_id']))
                conn.commit()
                conn.close()
            logged_in_users[session['user_id']]['name'] = new_name
            flash('Profile updated successfully.', 'success')
        return redirect(url_for('admin_profile'))
    
    return render_template('admin_profile.html', user_name=session['user_name'], user_email=session['user_email'])

@app.route('/admin/clear-activity-log', methods=['POST'])
@admin_required
def clear_activity_log():
    try:
        conn = sqlite3.connect('resume_builder.db')
        c = conn.cursor()
        c.execute('DELETE FROM activity_log')
        c.execute('INSERT INTO activity_log (action, user_id) VALUES (?, ?)',
                 ("Cleared activity log", session['user_id']))
        conn.commit()
        conn.close()
        flash('Activity log cleared successfully.', 'success')
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error in clear_activity_log: {str(e)}")
        flash('An error occurred while clearing the activity log.', 'error')
        return redirect(url_for('admin_dashboard'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error="Internal server error"), 500

@app.route('/error')
def error_page():
    error_message = request.args.get('error', 'An unknown error occurred')
    return render_template('error.html', error=error_message)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)  # Disable debug to avoid thread errors
