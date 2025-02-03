import jwt
from fastapi import HTTPException, Security
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, timedelta

# Define your secret key and algorithm
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"

# FastAPI's OAuth2 password bearer scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")  # Update to match the actual login endpoint

def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=30)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        user_type = payload.get("type")

        if not user_id or not user_type:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        return {"user_id": int(user_id), "user_type": user_type}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

