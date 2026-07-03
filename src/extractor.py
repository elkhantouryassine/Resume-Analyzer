import zipfile
from pathlib import Path
from xml.etree import ElementTree


WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def extract_docx_text(file_path):
    paragraphs = []
    path = Path(file_path)

    try:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ValueError("DOCX illisible ou invalide.") from exc

    root = ElementTree.fromstring(document_xml)
    for paragraph in root.iter(f"{WORD_NAMESPACE}p"):
        parts = []
        for node in paragraph.iter():
            if node.tag == f"{WORD_NAMESPACE}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{WORD_NAMESPACE}tab":
                parts.append("\t")
            elif node.tag == f"{WORD_NAMESPACE}br":
                parts.append("\n")

        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)

    return "\n".join(paragraphs)


def extract_pdf_text(file_path):
    try:
        import fitz
    except Exception as exc:
        raise ValueError("Le support PDF requiert PyMuPDF. Installez pymupdf ou utilisez DOCX/TXT.") from exc

    text = ""
    with fitz.open(file_path) as pdf:
        for page in pdf:
            text += page.get_text()

    return text
