from server.config.config import settings


def repair_mojibake_text(text: str) -> str:
    if not text:
        return text

    def looks_mojibake(s: str) -> bool:
        if any(0x80 <= ord(ch) <= 0x9F for ch in s):
            return True
        suspicious = (
            "脙",
            "脗",
            "芒",
            "冒",
            "茂",
            "氓",
            "盲",
            "忙",
            "莽",
            "锟?",
            "茅聹",
            "猫娄",
            "茅垄",
            "猫炉",
            "茫聙",
        )
        return any(tok in s for tok in suspicious)

    if not looks_mojibake(text):
        return text

    for enc in ("latin-1", "cp1252"):
        try:
            fixed = text.encode(enc, errors="strict").decode("utf-8", errors="strict")
            if fixed and not looks_mojibake(fixed):
                return fixed
            if fixed:
                return fixed
        except Exception:
            continue
    return text


def should_drop_stt_text(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False

    tokens = [
        x.strip().lower()
        for x in str(getattr(settings, "stt_noise_blocklist", "") or "").split(",")
        if x.strip()
    ]
    if not tokens:
        return False

    lower = cleaned.lower()
    return any(tok in lower for tok in tokens)

