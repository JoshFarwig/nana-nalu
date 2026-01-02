from schemas.user_schema import UserCreate, UserResponse


class AuthService:
    def __init__(self, user_repository, token_service):
        self.user_repository = user_repository
        self.token_service = token_service  # Do I need a token service?

    def login(self, username: str, password: str):
        pass

    def register(self, user_data: UserCreate):
        pass
