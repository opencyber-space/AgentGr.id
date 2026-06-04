import os

DELEGATE_SERVER_URL = os.getenv("DELEGATE_SERVER_URL", "http://35.223.239.192:30725")


#   postgresql:///chatserver                   (Unix socket, peer auth)
#   postgresql://localhost/chatserver          (TCP, trust auth)
#   postgresql://user@host/chatserver          (TCP, no password, cert/trust auth)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql:///chatserver")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
