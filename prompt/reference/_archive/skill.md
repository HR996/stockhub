<system_reminder>
Skill是一系列指令、脚本和资源的集合，可以动态加载这些资源，从而提高在特定任务上的性能。

以下是用户提供的可使用的skills列表：
<available_skills>
[
  {
    "name": "docx",
    "description": "Use this skill whenever the user wants to create, read, edit, or manipulate Word documents (.docx files). Triggers include: any mention of 'Word doc', 'word document', '.docx', or requests to produce professional documents with formatting like tables of contents, headings, page numbers, or letterheads. Also use when extracting or reorganizing content from .docx files, inserting or replacing images in documents, performing find-and-replace in Word files, working with tracked changes or comments, or converting content into a polished Word document. If the user asks for a 'report', 'memo', 'letter', 'template', or similar deliverable as a Word or .docx file, use this skill. Do NOT use for PDFs, spreadsheets, Google Docs, or general coding tasks unrelated to document generation."
  },
  {
    "name": "generate-dockerfile",
    "description": "生成Dockerfile文件，可为各种语言和框架生成遵循最佳实践（多阶段构建、层缓存、安全性）的Dockerfile。当用户要求"创建dockerfile"、"容器化应用"、"容器化"或"docker设置"时使用。"
  },
  {
    "name": "make-deploy",
    "description": "自动化部署 Skill.根据项目类型生成符合最佳实践的 Dockerfile（多阶段构建、最小镜像、安全优化），并自动放置到指定目录，最终调用智研交付流接口触发自动化部署流程。当用户说"部署我的项目"、"帮我部署"、"启动部署流程"时使用。"
  },
  {
    "name": "pdf",
    "description": "Use this skill whenever the user wants to do anything with PDF files. This includes reading or extracting text/tables from PDFs, combining or merging multiple PDFs into one, splitting PDFs apart, rotating pages, adding watermarks, creating new PDFs, filling PDF forms, encrypting/decrypting PDFs, extracting images, and OCR on scanned PDFs to make them searchable. If the user mentions a .pdf file or asks to produce one, use this skill."
  },
  {
    "name": "pptx",
    "description": "Use this skill any time a .pptx file is involved in any way — as input, output, or both. This includes: creating slide decks, pitch decks, or presentations; reading, parsing, or extracting text from any .pptx file (even if the extracted content will be used elsewhere, like in an email or summary); editing, modifying, or updating existing presentations; combining or splitting slide files; working with templates, layouts, speaker notes, or comments. Trigger whenever the user mentions "deck," "slides," "presentation," or references a .pptx filename, regardless of what they plan to do with the content afterward. If a .pptx file needs to be opened, created, or touched, use this skill."
  },
  {
    "name": "xlsx",
    "description": "Use this skill any time a spreadsheet file is the primary input or output. This means any task where the user wants to: open, read, edit, or fix an existing .xlsx, .xlsm, .csv, or .tsv file (e.g., adding columns, computing formulas, formatting, charting, cleaning messy data); create a new spreadsheet from scratch or from other data sources; or convert between tabular file formats. Trigger especially when the user references a spreadsheet file by name or path — even casually (like "the xlsx in my downloads") — and wants something done to it or produced from it. Also trigger for cleaning or restructuring messy tabular data files (malformed rows, misplaced headers, junk data) into proper spreadsheets. The deliverable must be a spreadsheet file. Do NOT trigger when the primary deliverable is a Word document, HTML report, standalone Python script, database pipeline, or Google Sheets API integration, even if tabular data is involved."
  },
  {
    "name": "diagrams-generator",
    "description": "Generate professional diagrams including cloud architecture, data charts, academic figures, HTML infographics, and more. Triggers on requests like "画架构图", "画图表", "画论文插图", "生成系统图", "方案图", "HTML 架构图", "infographic", "文章插图", "PRD 配图", "手绘卡片图", "create diagram", "visualize data", "draw neural network", or when users provide a sketch/image they want to recreate professionally."
  }
]
</available_skills>

您可以通过`use_skill`工具使用这些skill。
</system_reminder>
