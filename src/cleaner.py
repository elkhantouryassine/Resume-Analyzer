import re


def clean_text(text):
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-zA-ZÀ-ÿ0-9+#. ]", " ", text)
    text = text.strip()
    return text
