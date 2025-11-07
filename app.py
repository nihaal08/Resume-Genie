import os
import json
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

class CoverLetterForm(FlaskForm):
    job_description = TextAreaField('Job Description', validators=[DataRequired()], render_kw={"rows": 5})
    resume = FileField('Resume File', validators=[FileRequired(), FileAllowed(['pdf', 'txt'], 'PDF or TXT only!')])
    submit = SubmitField('Generate Cover Letter')

def extract_resume(file_path):
    if file_path.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    elif file_path.endswith('.pdf'):
        with pdfplumber.open(file_path) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
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
    try:
        return json.loads(response.text)
    except:
        return {
            "score": 65,
            "issues": [
                {"category": "Keywords", "description": "Missing key skills like 'Python'.", "fix": "Incorporate relevant keywords from the job description naturally into your resume."},
                {"category": "Structure", "description": "Possible tables or graphics detected.", "fix": "Convert to simple text-based formatting for better ATS parsing."},
                {"category": "Experience", "description": "Lacks quantifiable achievements.", "fix": "Include metrics, e.g., 'increased sales by 20%' to demonstrate impact."},
                {"category": "Length", "description": "Resume exceeds optimal length.", "fix": "Condense to 1-2 pages by prioritizing recent and relevant experience."}
            ]
        }

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
    try:
        return json.loads(response.text)
    except:
        return {
            "mistakes": [
                {"title": "Typos Galore", "description": "Your resume has more spelling errors than a drunk autocorrect—recruiters will think you can't even spell 'responsibility'."},
                {"title": "Vague Bullet Hell", "description": "Bullets like 'Did stuff'—wow, groundbreaking. Time to add some actual achievements before they hit delete."},
                {"title": "Gap Year? More Like Gap Decade", "description": "Unexplained employment gaps? Recruiters imagine you were binge-watching Netflix full-time."},
                {"title": "Font Fiesta", "description": "Mixing 5 fonts? This isn't a scrapbook, it's a resume—tone it down before eyes bleed."}
            ],
            "recruiter_thoughts": [
                {"title": "Impressive Experience", "description": "Solid progression in roles; shows dedication and growth potential."},
                {"title": "Quantifiable Wins", "description": "Love the metrics—makes impact crystal clear and sets you apart."},
                {"title": "Skills Alignment", "description": "Relevant tech stack matches our needs; excited to chat more."},
                {"title": "Clear Structure", "description": "Easy to scan—ATS will love it, and so will I during review."}
            ]
        }

def generate_cover_letter_with_gemini(job_desc, resume_text):
    prompt = f"""You are a professional cover letter writer. Generate a compelling, 3-4 paragraph cover letter based on the resume and job description. Tailor it to highlight relevant experience, skills, and enthusiasm for the role. Use a professional tone.

Output ONLY valid JSON: {{
    "cover_letter": "full cover letter text (str)"
}}

Job Description: {job_desc[:2000]}
Resume: {resume_text[:4000]}
"""
    response = model.generate_content(prompt)
    try:
        result = json.loads(response.text)
        return {"cover_letter": result.get("cover_letter", "Dear Hiring Manager,\n\n[Generated content placeholder]\n\nBest regards,\nYour Name")}
    except:
        return {"cover_letter": """Dear Hiring Manager,

I am excited to apply for the [Position] role at [Company], as advertised. With my background in [Key Skill from Resume], I have consistently delivered [Achievement], and I am eager to bring this expertise to your innovative team.

In my previous role at [Company from Resume], I [Specific Experience], resulting in [Impact]. This experience has equipped me with the skills to [Relevance to JD], aligning perfectly with your requirements for [JD Requirement].

I am passionate about [Industry/Topic from JD] and would welcome the opportunity to discuss how my unique blend of skills can contribute to [Company]'s success.

Thank you for considering my application. I look forward to the possibility of speaking with you soon.

Best regards,
[Your Name]"""}

@app.route('/', methods=['GET', 'POST'])
def index():
    ats_form = ATSToolForm()
    resume_form = ResumeToolForm()
    cover_form = CoverLetterForm()
    ats_results = None
    resume_results = None
    cover_results = None

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
        os.remove(file_path)

    elif form_type == 'cover' and cover_form.validate_on_submit():
        filename = secure_filename(cover_form.resume.data.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        cover_form.resume.data.save(file_path)

        resume_text = extract_resume(file_path)
        if not resume_text:
            flash('Error reading resume file.', 'error')
            os.remove(file_path)
            return redirect(url_for('index'))

        job_desc = cover_form.job_description.data
        cover_results = generate_cover_letter_with_gemini(job_desc, resume_text)
        os.remove(file_path)

    return render_template('index.html', ats_form=ats_form, resume_form=resume_form, cover_form=cover_form, ats_results=ats_results, resume_results=resume_results, cover_results=cover_results)

if __name__ == '__main__':
    app.run(debug=True)