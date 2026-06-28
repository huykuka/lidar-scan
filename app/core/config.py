import os


class Settings:
    # API Settings
    PROJECT_NAME: str = "Lidar Studio API"
    VERSION: str = "2.0.6"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8005))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"


settings = Settings()
