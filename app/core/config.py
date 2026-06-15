import os


class Settings:
    # API Settings
    PROJECT_NAME: str = "Lidar Standalone API"
    VERSION: str = "2.0.3"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8005))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    # Directory Settings
    DEBUG_OUTPUT_DIR: str = "debug_data"


settings = Settings()
