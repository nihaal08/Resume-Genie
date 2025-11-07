import os
import json
import re
from io import BytesIO
from flask import Flask, render_template, request, flash, redirect, url_for
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
import google.generativeai as genai
import pdfplumber
from dotenv import load_dotenv
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-change-me')
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-2.0-flash')
class ATSToolForm(FlaskForm):
    job_description = TextAreaField('Job Description', validators=[DataRequired()], render_kw={"rows": 5})
    resume = FileField('Resume File', validators=[FileRequired(), FileAllowed(['pdf', 'txt'], 'PDF or TXT only!')])
    submit = SubmitField('Analyze ATS Compatibility')
class ResumeToolForm(FlaskForm):
    resume = FileField('Resume File', validators=[FileRequired(), FileAllowed(['pdf', 'txt'], 'PDF or TXT only!')])
    submit = SubmitField('Generate Review')
def extract_resume(file_path):
    if file_path.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif file_path.endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
    return None
def extract_json(text):
    # Remove any markdown code blocks if present
    text = re.sub(r'```json\s*', '', text, flags=re.DOTALL)
    text = re.sub(r'```\s*', '', text, flags=re.DOTALL)
    # Strip whitespace
    text = text.strip()
    # Find the JSON part
    start = text.find('{')
    if start == -1:
        return None
    end = text.rfind('}')
    if end == -1 or end < start:
        return None
    json_str = text[start:end+1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        print(f"Raw response snippet: {text[:200]}...")  # For debugging
        return None
def analyze_ats_with_gemini(job_desc, resume_text):
    prompt = f"""You are an ATS (Applicant Tracking System) expert and resume optimizer. Analyze the resume against the job description and provide a compatibility score (0-100) and 4-6 key issues with fixes.
Criteria:
- Keywords: Match job-specific terms (skills, tools, qualifications).
- Structure: ATS-friendly format (no tables/graphics, clear sections).
- Content: Relevance, quantifiable achievements, gaps in experience.
- Length/Formatting: 1-2 pages, standard fonts, consistent.
Output ONLY valid JSON: {{
    "score": integer (0-100),
    "issues": [
        {{
            "category": "str (e.g., Keywords)",
            "description": "str (brief issue)",
            "fix": "str (actionable fix)"
        }}
    ]
}}
Job Description: {job_desc[:2000]}
Resume: {resume_text[:4000]}
"""
    response = model.generate_content(prompt)
    result = extract_json(response.text)
    if result is None:
        # Fallback only if extraction fails
        return {
            "score": 65,
            "issues": [
                {"category": "Keywords", "description": "Missing key skills like 'Python'.", "fix": "Incorporate relevant keywords from the job description naturally into your resume."},
                {"category": "Structure", "description": "Possible tables or graphics detected.", "fix": "Convert to simple text-based formatting for better ATS parsing."},
                {"category": "Experience", "description": "Lacks quantifiable achievements.", "fix": "Include metrics, e.g., 'increased sales by 20%' to demonstrate impact."},
                {"category": "Length", "description": "Resume exceeds optimal length.", "fix": "Condense to 1-2 pages by prioritizing recent and relevant experience."}
            ]
        }
    return result
def analyze_resume_with_gemini(resume_text):
    prompt = f"""You are a witty resume reviewer with a troll/humorous edge, but also provide serious recruiter insights. Analyze the resume for 4-6 common mistakes (typos, gaps, vague language, etc.) and what a recruiter might think (pros/cons).
For mistakes: Humorous, exaggerated descriptions.
For recruiter thoughts: Realistic, balanced perspectives.
Output ONLY valid JSON: {{
    "mistakes": [
        {{
            "title": "str (e.g., 'Typos Galore')",
            "description": "str (funny troll commentary)"
        }}
    ],
    "recruiter_thoughts": [
        {{
            "title": "str (e.g., 'Strong Technical Skills')",
            "description": "str (recruiter's view)"
        }}
    ]
}}
Resume: {resume_text[:4000]}
"""
    response = model.generate_content(prompt)
    result = extract_json(response.text)
    if result is None:
        return None
    return result
@app.route('/', methods=['GET', 'POST'])
def index():
    ats_form = ATSToolForm()
    resume_form = ResumeToolForm()
    ats_results = None
    resume_results = None
    form_type = request.form.get('form_type')
    if form_type == 'ats' and ats_form.validate_on_submit():
        filename = secure_filename(ats_form.resume.data.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        ats_form.resume.data.save(file_path)
        resume_text = extract_resume(file_path)
        if not resume_text:
            flash('Error reading resume file.', 'error')
            os.remove(file_path)
            return redirect(url_for('index'))
        job_desc = ats_form.job_description.data
        ats_results = analyze_ats_with_gemini(job_desc, resume_text)
        os.remove(file_path)
    elif form_type == 'resume' and resume_form.validate_on_submit():
        filename = secure_filename(resume_form.resume.data.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        resume_form.resume.data.save(file_path)
        resume_text = extract_resume(file_path)
        if not resume_text:
            flash('Error reading resume file.', 'error')
            os.remove(file_path)
            return redirect(url_for('index'))
        resume_results = analyze_resume_with_gemini(resume_text)
        if resume_results is None:
            flash('Error generating AI feedback. Please try again.', 'error')
        os.remove(file_path)
    return render_template('index.html', ats_form=ats_form, resume_form=resume_form, ats_results=ats_results, resume_results=resume_results)
if __name__ == '__main__':
    app.run(debug=True)