import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    # Get configuration from settings
    port = settings.PORT
    host = settings.HOST
    
    print(f"Starting {settings.PROJECT_NAME} on {host}:{port}")
    
    uvicorn.run(
        "app.app:app", 
        host=host, 
        port=port, 
        reload=settings.DEBUG
    )
