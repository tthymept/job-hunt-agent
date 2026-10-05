export const STATUS = [
  "Saved / Not Applied","Submitted","Online Assignment",
  "Interview Round 1","Interview Round 2","Offered","Rejected"
];

export const ST_CLASS = {
  "Saved / Not Applied":"saved","Submitted":"sub","Online Assignment":"online",
  "Interview Round 1":"int1","Interview Round 2":"int2","Offered":"off","Rejected":"rej"
};

export const initialJobs = [
  {co:"Agoda",title:"Data Engineering Intern",loc:"Singapore",dur:"18 May – 17 July",min:"2 months",dl:"24 Oct 2026",status:"Online Assignment",agent:"Agoda_Tailored.pdf",upload:"AlexTan_CV.pdf",
   skills:["Python","SQL","PySpark","Data Engineering","Machine Learning","Power BI"],
   jd:"Join Agoda's Data Engineering team to build reliable, scalable datasets that support travel products used worldwide. You will work alongside engineers and analysts to develop batch and streaming pipelines, improve data quality, and translate business questions into durable data models.",
   bullets:["Built PySpark pipelines processing 4M+ daily records, improving reporting freshness by 35%.","Designed dimensional SQL models and automated data-quality checks for 12 analytics tables.","Partnered with analysts to ship Power BI dashboards used by three product teams."]},
  {co:"Grab",title:"Data Science Intern",loc:"Singapore",dur:"Jan – Jun 2027",min:"5 months",dl:"28 Oct 2026",status:"Interview Round 1",agent:"Grab_Tailored.pdf",upload:"CV_v4.pdf",
   skills:["Python","A/B Testing","SQL","Forecasting"],jd:"Support Grab's data science team with experimentation design and demand forecasting across Southeast Asia's mobility and delivery markets.",
   bullets:["Ran A/B tests informing pricing decisions across two city markets.","Built a demand forecasting model improving MAPE by 9 points."]},
  {co:"DBS",title:"Analytics Intern",loc:"Singapore",dur:"12 Jan – 30 Jun",min:"5 months",dl:"02 Nov 2026",status:"Submitted",agent:"DBS_Tailored.pdf",upload:"DBS_CV.pdf",
   skills:["SQL","Power BI","Risk Analytics"],jd:"Support DBS's analytics team building dashboards and risk-monitoring reports for retail banking products.",
   bullets:["Automated a weekly risk report, saving 4 analyst-hours per week.","Built a Power BI dashboard adopted by two business units."]},
  {co:"Shopee",title:"Machine Learning Intern",loc:"Singapore",dur:"Jan – May 2027",min:"4 months",dl:"07 Nov 2026",status:"Interview Round 2",agent:"Shopee_Tailored.pdf",upload:"AlexTan_CV.pdf",
   skills:["Python","ML","Recommender Systems"],jd:"Work on recommendation and ranking models powering Shopee's product discovery experience.",
   bullets:["Improved click-through rate 6% via feature engineering on a ranking model.","Deployed a recommender A/B test across 3 markets."]},
  {co:"Huawei",title:"AI Research Intern",loc:"Bangkok",dur:"Feb – Jul 2027",min:"6 months",dl:"12 Nov 2026",status:"Saved / Not Applied",agent:"Huawei_Tailored.pdf",upload:null,
   skills:["PyTorch","Research","NLP"],jd:"Contribute to applied NLP research projects within Huawei's regional AI research lab.",
   bullets:["Reproduced a published baseline and improved F1 by 4 points.","Co-authored an internal technical report on model distillation."]},
  {co:"TikTok",title:"Product Data Intern",loc:"Singapore",dur:"Jan – Jun 2027",min:"5 months",dl:"15 Nov 2026",status:"Offered",agent:"TikTok_Tailored.pdf",upload:"TikTok_CV.pdf",
   skills:["SQL","Experimentation","Product Analytics"],jd:"Partner with product managers to analyze engagement metrics and support experimentation across content features.",
   bullets:["Built a metrics pipeline tracked by three product squads.","Analyzed an experiment that shipped to 100% rollout."]},
  {co:"Sea Labs",title:"Backend Engineer Intern",loc:"Singapore",dur:"May – Aug 2027",min:"3 months",dl:"19 Nov 2026",status:"Rejected",agent:"SeaLabs_Tailored.pdf",upload:"CV_v3.pdf",
   skills:["Java","Distributed Systems","APIs"],jd:"Build backend services supporting Sea Labs' internal platform tooling.",
   bullets:["Implemented a caching layer reducing API latency by 20%.","Wrote integration tests raising coverage to 80%."]},
];

export const initialExploreJobs = [
  {num:"J-1048",co:"Google",title:"Data Analytics Intern",loc:"Singapore",dur:"Jan – Jun 2027",min:"5 months",dl:"26 Oct 2026",src:"LinkedIn"},
  {num:"J-1047",co:"ByteDance",title:"Machine Learning Engineer Intern",loc:"Singapore",dur:"May – Aug 2027",min:"3 months",dl:"30 Oct 2026",src:"Careers",added:true},
  {num:"J-1046",co:"AirAsia",title:"Business Intelligence Intern",loc:"Bangkok",dur:"Jan – May 2027",min:"4 months",dl:"03 Nov 2026",src:"LinkedIn"},
  {num:"J-1045",co:"Microsoft",title:"Cloud Solution Intern",loc:"Singapore",dur:"May – Aug 2027",min:"12 weeks",dl:"06 Nov 2026",src:"Careers"},
  {num:"J-1044",co:"Lazada",title:"Product Analytics Intern",loc:"Singapore",dur:"Jan – Jun 2027",min:"5 months",dl:"08 Nov 2026",src:"Glints"},
  {num:"J-1043",co:"LINE MAN Wongnai",title:"Data Science Intern",loc:"Bangkok",dur:"Feb – Jul 2027",min:"5 months",dl:"12 Nov 2026",src:"JobsDB"},
  {num:"J-1042",co:"GovTech",title:"Software Engineer Intern",loc:"Singapore",dur:"Jan – May 2027",min:"4 months",dl:"14 Nov 2026",src:"Careers"},
];
