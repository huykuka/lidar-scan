import uvicorn
import os

if __name__ == "__main__":
    # Get configuration from env
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"Starting Lidar Standalone Application on {host}:{port}")
    
    uvicorn.run(
        "app.app:app", 
        host=host, 
        port=port, 
        reload=True if os.getenv("DEBUG") == "true" else False
    )
