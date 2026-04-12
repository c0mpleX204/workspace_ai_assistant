RULES=[
    {
        "id": "answer_style_concise",
        "type": "preference",
        "keywords": ["简洁", "短一点", "别太长", "简短"],
        "key": "answer_style",
        "value": "concise",
        "confidence": 0.7,
    },
    {
        "id": "deadline_progress",
        "type": "progress",
        "keywords": ["ddl", "截止", "考试", "测验", "作业", "复习", "deadline"],
        "topic": "deadline_or_exam",
        "status": "learning",
        "mastery": 0.2,
        "confidence": 0.6,
    },
    {
        "id": "language_preference_keyword",
        "type": "preference",
        "keywords": ["请用英文", "用英文回答", "英文回答", "请用中文", "用中文回答", "中文回答"],
        "key": "language",
        "map": {"中文": "zh", "英文": "en"},
        "confidence": 0.8,
    },
    {
      "id": "language_preference_regex",
      "type": "preference",
      "regex": r"我喜欢(?:使用)?\s*(中文|英文)",
      "key": "language",
      "map": {"中文":"zh","英文":"en"},
      "confidence": 0.85,
    }

]

def normalize_pref_signal(raw_signal: dict) -> dict:
    """
    将从规则匹配得到的原始信号标准化为:
    {key, value, source, confidence, rule_id, normalized_value}
    """
    key = raw_signal.get("key")
    value = raw_signal.get("value")
    confidence = float(raw_signal.get("confidence", 0.5))
    source = raw_signal.get("source", "rule")
    # 简单归一化示例：将中文“中文/英文”转成 zh/en
    if isinstance(value, str):
        v = value.strip()
        if v in ("中文", "chinese"):
            nv = "zh"
        elif v in ("英文", "english"):
            nv = "en"
        else:
            nv = v
    else:
        nv = value
    return {
        "key": key,
        "value": value,
        "normalized_value": nv,
        "source": source,
        "confidence": confidence,
        "rule_id": raw_signal.get("rule_id"),
    }
