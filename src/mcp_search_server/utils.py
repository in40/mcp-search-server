def sanitize_text(text: str, max_length: int = 10000) -> str:
    if not text:
        return ""

    if isinstance(text, bytes):
        try:
            text = text.decode('utf-8', errors='ignore')
        except Exception:
            text = text.decode('latin-1', errors='ignore')

    text = str(text)
    text = text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t\r')

    if len(text) > max_length:
        text = text[:max_length]

    return text.strip()
