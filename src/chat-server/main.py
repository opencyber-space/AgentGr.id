import uvicorn
from core.app import create_app
from core.config import HOST, PORT

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
