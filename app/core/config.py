import os

class Settings:
    # API Settings
    PROJECT_NAME: str = "Lidar Standalone API"
    VERSION: str = "1.3.0"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", 8005))
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # LIDAR Settings
    LIDAR_MODE: str = os.getenv("LIDAR_MODE", "real")  # "real" or "sim"
    LIDAR_IP: str = os.getenv("LIDAR_IP", "192.168.100.123")
    LIDAR_LAUNCH: str = os.getenv("LIDAR_LAUNCH", "./launch/sick_multiscan.launch")
    LIDAR_PCD_PATH: str = os.getenv("LIDAR_PCD_PATH", "./test.pcd")

    # Directory Settings
    DEBUG_OUTPUT_DIR: str = "debug_data"

settings = Settings()
