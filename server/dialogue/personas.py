from typing import Dict

from server.dialogue.prompts import DEFAULT_PERSONA_PROMPT

PERSONAS:Dict[str,Dict[str,str]]={
    "student_friend":{
        "id":"student_friend",
        "system_prompt": DEFAULT_PERSONA_PROMPT,
    },
    "concise_tutor":{
        "id":"concise_tutor",
        "system_prompt":(
            "你是教学助理，语气严谨但友好。回答应直奔要点，提供简短步骤。"
            "每条建议尽可能用序号或短句呈现。"
        )
    }

}
