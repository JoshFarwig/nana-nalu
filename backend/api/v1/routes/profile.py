from fastapi import APIRouter

router = APIRouter(prefix="/profile", tags=["users"])

# NOTE: Cloudflare R2 for profile pic / surf spot photos?


@router.get("/me")
def get_current_user_profile():
    pass


@router.get("/me/friends")
def get_user_friends():
    pass


@router.get("/{username}")
def get_user_profile(username: str):
    pass


@router.put("/me")
def update_user_profile():
    pass


# TODO: setup cloudflare R2 for profile pic?
# @router.post("/me/avatar")
# def upload_profile_picture():
#     pass
