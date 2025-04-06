from flask import Flask, render_template, request, send_file, redirect, url_for, flash, session, Response
import pdfkit
from pdfkit.configuration import Configuration
import os
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key_for_testing')

# Gmail credentials for OTP
EMAIL_ADDRESS = "dropafile07@gmail.com"
EMAIL_PASSWORD = "fmxa crxm cdqf lbfn"  # App-specific password

# Hardcoded admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("admin123")

# In-memory stores
logged_in_users = {}
otp_storage = {}  # For OTPs (use Redis or DB in production)

# Database initialization
def init_db():
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
    conn.close()

# Initialize database on startup
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
if os.name == 'nt':  # Windows
    WKHTMLTOPDF_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
else:  # Linux/Mac
    WKHTMLTOPDF_PATH = '/usr/local/bin/wkhtmltopdf'

if os.path.exists(WKHTMLTOPDF_PATH):
    config = Configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
else:
    logger.warning(f"wkhtmltopdf not found at {WKHTMLTOPDF_PATH}. PDF generation may fail.")
    config = None

# Ensure download directory exists
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
    return render_template('index.html')

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
            if c.fetchone() is not None:
                flash('Email already registered.', 'error')
                return redirect(url_for('register'))

            # Generate and store OTP
            otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
            otp_storage[email] = {'otp': otp, 'password': generate_password_hash(password), 'full_name': full_name}

            # Send OTP email
            subject = "Your OTP for ATC Resume Builder Registration"
            body = f"Your OTP is: {otp}\nPlease use this to complete your registration.\nThis OTP expires in 10 minutes."
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
                # Generate and store OTP
                otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
                otp_storage[email] = {'otp': otp, 'user_id': user[0]}

                # Send OTP email
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
    # [Existing code remains unchanged]
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
    # [Existing code remains unchanged]
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
    app.run(host='0.0.0.0', port=port, debug=True)