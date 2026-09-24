from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    DATABASE_URL: str
    GROQ_API_KEY: str
    VAPI_API_KEY: str = ""
    RAILWAY_URL: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
