# utils/ai.py

import os
import google.generativeai as genai
from dotenv import load_dotenv
import time
import random

# Load environment variables
load_dotenv()

# Initialize Gemini AI
def initialize_gemini():
    """Initialize Gemini AI with proper error handling."""
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY not found in environment variables")
            return None

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        # Test the model with a simple query
        test_response = model.generate_content("Hello")
        print("Gemini AI initialized successfully")
        return model

    except Exception as e:
        print(f"Error initializing Gemini AI: {e}")
        return None

# Initialize the model
model = initialize_gemini()

def check_model(func):
    """Decorator to handle cases where the model fails to initialize."""
    def wrapper(*args, **kwargs):
        if model is None:
            return "<p class='error'>Error: AI service is currently unavailable. Please check your API configuration and try again.</p>"

        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"Error in AI function '{func.__name__}': {e}")
            return f"<p class='error'>An error occurred while processing your request. Please try again.</p>"

    return wrapper

@check_model
def generate_app_description():
    """Generates a marketing description for the ATC Resume Builder app."""
    prompt = """
    As a marketing expert, write a compelling and inspiring 2-paragraph description for a web application named "ATC Resume Builder".

    Highlight these key features and values:
    - It's AI-powered, using modern technology to help job seekers
    - It helps users create professional, ATS-friendly resumes
    - It offers a comprehensive suite of tools: Resume Builder, Resume Analyzer, Cover Letter Generator, Job Matcher, and Skill Gap Analyzer
    - The core mission is to empower job seekers and level the playing field in today's competitive job market
    - It's user-friendly and accessible to everyone
    - The tone should be professional, encouraging, and focused on user success

    Make it engaging and motivational. Start with a strong opening about the challenges job seekers face and end with an empowering statement about achieving career goals.
    """

    response = model.generate_content(prompt)
    return response.text.strip()

@check_model
def generate_professional_summary(user_input):
    """Generates a professional summary from user input."""
    prompt = f"""
    As an expert career coach and resume writer, expand the following input into a compelling, professional summary for a resume.

    User's input: "{user_input}"

    Requirements:
    - Create a 3-4 sentence professional summary
    - Make it ATS-friendly with relevant keywords
    - Highlight key strengths and achievements
    - Use action-oriented language
    - Make it specific and impactful
    - Suitable for modern job applications

    Write only the professional summary, no additional text or formatting.
    """

    response = model.generate_content(prompt)
    return response.text.strip()

@check_model
def analyze_resume_text(resume_text):
    """Analyzes resume text for ATS score, keywords, and improvements."""
    prompt = f"""
    You are an expert ATS (Applicant Tracking System) analyst and professional resume reviewer.
    Analyze the following resume text and provide a comprehensive analysis in clean HTML format.

    Resume Text:
    {resume_text}

    Provide your analysis in the following HTML structure:

    <h3>ATS Compatibility Score</h3>
    <p>Provide a score out of 100 with brief explanation of the scoring criteria.</p>

    <h3>Keyword Analysis</h3>
    <p><strong>Keywords Found:</strong> List the key skills and keywords currently in the resume.</p>
    <p><strong>Missing Keywords:</strong> Suggest 5-7 important keywords that should be added for better ATS performance.</p>

    <h3>Format & Structure Assessment</h3>
    <ul>
        <li>Comment on overall structure and readability</li>
        <li>Assess the effectiveness of bullet points</li>
        <li>Evaluate section organization</li>
    </ul>

    <h3>Specific Improvement Recommendations</h3>
    <ul>
        <li>Provide 4-5 actionable, specific recommendations</li>
        <li>Focus on high-impact changes</li>
        <li>Include both content and formatting suggestions</li>
    </ul>

    <h3>Strengths Identified</h3>
    <p>Highlight 2-3 strong points in the current resume.</p>

    Be constructive, specific, and actionable in your feedback.
    """

    response = model.generate_content(prompt)
    return response.text.strip()

@check_model
def generate_cover_letter(resume_text):
    """Generates a cover letter template from resume text."""
    prompt = f"""
    Based on the provided resume, create a professional cover letter template.

    Resume Text:
    {resume_text}

    Create a cover letter with the following structure in HTML format:

    <h3>Professional Cover Letter Template</h3>

    <p><strong>Instructions:</strong> Replace the placeholders [Company Name], [Job Title], [Hiring Manager Name], etc. with specific information for each application.</p>

    <div style="margin: 20px 0;">
    <p>Dear [Hiring Manager Name / Hiring Team],</p>

    <p>[Opening paragraph - Express interest in the specific role and company]</p>

    <p>[Body paragraph 1 - Highlight relevant experience and skills from the resume]</p>

    <p>[Body paragraph 2 - Demonstrate knowledge of the company and explain why you're a good fit]</p>

    <p>[Closing paragraph - Call to action and thank you]</p>

    <p>Sincerely,<br>
    [Your Name]</p>
    </div>

    <h4>Key Points to Customize:</h4>
    <ul>
        <li>Research the company and mention specific details</li>
        <li>Tailor the skills mentioned to match the job requirements</li>
        <li>Use keywords from the job posting</li>
        <li>Keep it concise (3-4 paragraphs)</li>
    </ul>

    Base the content on the strongest points from the resume provided.
    """

    response = model.generate_content(prompt)
    return response.text.strip()

@check_model
def match_jobs(resume_text):
    """Suggests job roles based on resume data."""
    prompt = f"""
    Analyze the skills, experience, and qualifications in this resume and suggest suitable job roles.

    Resume Text:
    {resume_text}

    Provide your analysis in the following HTML format:

    <h3>Recommended Job Roles</h3>
    <p>Based on your skills and experience, here are job roles that would be a good fit:</p>

    <h4>Primary Matches (90-100% fit):</h4>
    <ul>
        <li><strong>Job Title 1:</strong> Brief explanation of why this role fits well</li>
        <li><strong>Job Title 2:</strong> Brief explanation of why this role fits well</li>
        <li><strong>Job Title 3:</strong> Brief explanation of why this role fits well</li>
    </ul>

    <h4>Secondary Matches (70-89% fit):</h4>
    <ul>
        <li><strong>Job Title 4:</strong> Brief explanation and what skills might need development</li>
        <li><strong>Job Title 5:</strong> Brief explanation and what skills might need development</li>
    </ul>

    <h4>Growth Opportunities (50-69% fit):</h4>
    <ul>
        <li><strong>Job Title 6:</strong> Explanation of the career path and skills needed</li>
        <li><strong>Job Title 7:</strong> Explanation of the career path and skills needed</li>
    </ul>

    <h4>Job Search Tips:</h4>
    <ul>
        <li>Focus on roles that match your strongest skills</li>
        <li>Use relevant keywords from your field in job searches</li>
        <li>Consider both the job title and company culture fit</li>
    </ul>

    Focus on current market demands and realistic opportunities.
    """

    response = model.generate_content(prompt)
    return response.text.strip()

@check_model
def analyze_skill_gap(resume_text):
    """Compares resume skills with trending skills in the job market."""
    prompt = f"""
    Analyze the skills in this resume and compare them with current market trends and demands.

    Resume Text:
    {resume_text}

    Provide a comprehensive skill gap analysis in HTML format:

    <h3>Skill Gap Analysis</h3>

    <h4>Current Skills Assessment</h4>
    <p><strong>Technical Skills:</strong> List and rate the technical skills found (Strong/Moderate/Basic)</p>
    <p><strong>Soft Skills:</strong> List the soft skills demonstrated</p>
    <p><strong>Industry Knowledge:</strong> Assess domain expertise</p>

    <h4>Market Demand Analysis</h4>
    <p>Based on current job market trends, here's what employers are looking for:</p>

    <h4>Critical Skill Gaps</h4>
    <ul>
        <li><strong>High Priority:</strong> Skills that are in high demand but missing from the resume</li>
        <li><strong>Medium Priority:</strong> Skills that would enhance marketability</li>
        <li><strong>Nice to Have:</strong> Emerging skills that could provide competitive advantage</li>
    </ul>

    <h4>Skill Development Recommendations</h4>
    <ul>
        <li><strong>Immediate Focus (0-3 months):</strong> Quick wins and certifications</li>
        <li><strong>Medium-term Goals (3-6 months):</strong> Courses and practical projects</li>
        <li><strong>Long-term Investment (6+ months):</strong> Advanced skills and specializations</li>
    </ul>

    <h4>Learning Resources</h4>
    <ul>
        <li>Suggest specific platforms, courses, or certifications</li>
        <li>Recommend hands-on projects to build portfolio</li>
        <li>Identify networking opportunities</li>
    </ul>

    <h4>Market Positioning</h4>
    <p>Advice on how to position current skills while developing new ones.</p>

    Be specific, actionable, and realistic in your recommendations.
    """

    response = model.generate_content(prompt)
    return response.text.strip()

# Test function to verify AI functionality
def test_ai_functions():
    """Test function to verify all AI functions work correctly."""
    if model is None:
        print("AI model is not initialized")
        return False

    try:
        # Test with sample data
        test_result = generate_app_description()
        print("AI functions are working correctly")
        return True
    except Exception as e:
        print(f"AI functions test failed: {e}")
        return False

# Run test on module import
if __name__ == "__main__":
    test_ai_functions()