from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="Learner", min_length=1, max_length=120)
    role: Literal["student", "teacher"] = "student"

    @field_validator("password")
    @classmethod
    def validate_strength(cls, v: str) -> str:
        has_upper = any(c.isupper() for c in v)
        has_lower = any(c.islower() for c in v)
        has_digit = any(c.isdigit() for c in v)
        if not (has_upper and has_lower and has_digit):
            raise ValueError("Password must include uppercase, lowercase, and at least one number.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_strength(cls, v: str) -> str:
        return SignupRequest.validate_strength(v)


class GoogleAuthRequest(BaseModel):
    id_token: str = Field(min_length=10)


class UserProfileResponse(BaseModel):
    full_name: str
    grade_level: str
    subjects: list[str]
    learning_goal: str
    preferred_language: Literal["en", "hi", "kn"]
    theme: Literal["light", "dark"]
    leaderboard_opt_in: bool
    xp: int
    level: int
    streak_days: int
    weekly_goal_target: int
    weekly_progress: int
    onboarding_completed: bool


class UserResponse(BaseModel):
    id: str
    email: str
    role: Literal["student", "teacher"]
    profile: UserProfileResponse


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    grade_level: str | None = Field(default=None, min_length=1, max_length=64)
    subjects: list[str] | None = Field(default=None, max_length=12)
    learning_goal: str | None = Field(default=None, min_length=1, max_length=255)
    preferred_language: Literal["en", "hi", "kn"] | None = None
    theme: Literal["light", "dark"] | None = None
    leaderboard_opt_in: bool | None = None
    weekly_goal_target: int | None = Field(default=None, ge=1, le=50)
    onboarding_completed: bool | None = None
