from server.api.schemas import SkillItem, SkillListResponse
from server.services.skill_registry import list_installed_skills

from fastapi import APIRouter


router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=SkillListResponse)
def api_list_skills() -> SkillListResponse:
    items = [SkillItem(**item) for item in list_installed_skills()]
    return SkillListResponse(items=items, total=len(items))

