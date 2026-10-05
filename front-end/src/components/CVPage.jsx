import { useState } from 'react'

// Old version: a manual addEventListener on #dropzone that called
// .click() on a hidden <input>, plus another listener that reached
// into the DOM to overwrite #fname and #fmeta's textContent.
// Here, filename/filesize live in useState, and the <label htmlFor>
// trick triggers the hidden input without any JS click handler at all.
export default function CVPage() {
  const [fileName, setFileName] = useState('Alex_Tan_CV_2026.pdf')
  const [fileMeta, setFileMeta] = useState('Updated 2 October 2026 · 248 KB')

  function handleFileChange(e) {
    const file = e.target.files[0]
    if (file) {
      setFileName(file.name)
      setFileMeta(`Just now · ${(file.size / 1024).toFixed(0)} KB`)
    }
  }

  return (
    <section>
      <div className="pagehead">
        <div>
          <h1>My CV</h1>
          <p>Upload one master CV to preview, download, and tailor for applications.</p>
        </div>
        <button className="btn primary">⬇ Download</button>
      </div>

      <label className="dropzone" htmlFor="fileInput" style={{ display: 'block' }}>
        <div className="ic">⬆</div>
        <div><strong>Drop your CV here or browse files</strong></div>
        <div style={{ fontSize: 12, marginTop: 4 }}>PDF or DOCX · Maximum 10 MB</div>
        <input id="fileInput" type="file" style={{ display: 'none' }} accept=".pdf,.docx" onChange={handleFileChange} />
      </label>

      <div className="fileinfo">
        <div>
          📄 <span className="name">{fileName}</span><br/>
          <span className="sub">{fileMeta}</span>
        </div>
        <div className="actions">
          <button className="btn sm">↻ Replace</button>
          <button className="btn sm">⬇ Download</button>
        </div>
      </div>

      <div className="card" style={{ background: 'var(--row-hover)', padding: 30 }}>
        <div className="resume">
          <h2>ALEX TAN</h2>
          <div className="role">DATA ENGINEERING &amp; ANALYTICS</div>
          <div className="contact">Singapore · alex.tan@email.com · +65 9123 4567 · linkedin.com/in/alextan</div>

          <h3>PROFILE</h3>
          <p style={{ fontSize: 12.5, color: '#374151', margin: 0 }}>
            Computer Science undergraduate with hands-on experience building data pipelines, analytics
            models, and internal BI products. Comfortable with Python, SQL, PySpark, and cloud data
            tooling; motivated by reliable systems and measurable product outcomes.
          </p>

          <h3>EXPERIENCE</h3>
          <div className="entry">Data Engineering Intern — Nimble Analytics <span>May – Aug 2026</span></div>
          <ul>
            <li>Built PySpark ETL pipelines processing 4M+ daily records and reduced reporting latency by 35%.</li>
            <li>Implemented automated data-quality tests for 12 core tables, cutting recurring incidents by 28%.</li>
            <li>Partnered with product analysts to model customer funnels and publish Power BI dashboards.</li>
          </ul>
          <div className="entry">Research Assistant — NUS Computing <span>Jan – Apr 2026</span></div>
          <ul>
            <li>Trained classification models for mobility datasets and improved F1 score from 0.78 to 0.86.</li>
            <li>Documented reproducible Python workflows and presented findings to a six-person research group.</li>
          </ul>

          <h3>PROJECTS</h3>
          <div className="entry">CampusPulse — Event demand forecasting <span>2026</span></div>
          <ul><li>Designed an Airflow pipeline and gradient-boosted forecast model using 1.2M event and attendance records.</li></ul>
          <div className="entry">SpendScope — Personal finance analytics <span>2025</span></div>
          <ul><li>Built a privacy-first transaction categorizer and React dashboard with 91% classification accuracy.</li></ul>

          <h3>EDUCATION &amp; SKILLS</h3>
          <div className="entry">B.Comp. Computer Science, National University of Singapore <span>2024 – 2027</span></div>
          <p style={{ fontSize: 12, color: '#6b7280', margin: '4px 0 0' }}>
            Python · SQL · PySpark · Pandas · Airflow · Power BI · Git · AWS · Machine Learning
          </p>
        </div>
      </div>
    </section>
  )
}
