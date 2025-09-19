from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def list_users():
    return [{"username": "alice"}]


@router.post("/")
def create_user(user: dict):
    return user
