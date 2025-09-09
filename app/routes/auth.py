from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.errors import DuplicateKeyError
from ..schemas import RegisterIn, TokenOut, UserOut, GenerateSecretOut
from ..database import db
from ..auth import hash_password, verify_password, create_access_token
from datetime import date
import secrets
from bson import ObjectId
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# plan limits: plan_id -> monthly calls
PLANS = {0: 10, 1: 20, 2: 30}

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError, PyMongoError
from datetime import date
from bson import ObjectId

router = APIRouter()

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterIn):
    """
    Registers a new user with username & password.
    Creates an associated usage document for tracking API usage.
    """

    # Step 1: Check if user already exists
    try:
        existing_user = await db.users.find_one({"username": data.username})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error while checking existing user: {str(e)}"
        )

    # Step 2: Prepare user document
    user_doc = {
        "username": data.username,
        "password": hash_password(data.password),
        "plan": 0,
        "secret_token": None,
        "created_at": date.today().isoformat(),
        "updated_at": date.today().isoformat(),
    }

    try:
        # Step 3: Insert user
        result = await db.users.insert_one(user_doc)

        if not result.inserted_id or not isinstance(result.inserted_id, ObjectId):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user record"
            )

        # Step 4: Create usage document
        usage_doc = {
            "user_id": result.inserted_id,
            "calls_made_month": 0,
            "calls_today": 0,
            "last_day_reset": date.today().isoformat(),
            "last_month_reset": date.today().isoformat(),
        }
        await db.usage.insert_one(usage_doc)

        return {
            "msg": "User created successfully",
            "user_id": str(result.inserted_id)
        }

    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this username already exists"
        )

    except PyMongoError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.post("/login", response_model=TokenOut)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await db.users.find_one({"username": form_data.username})
    if not user or not verify_password(form_data.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect credentials")
    token = create_access_token(subject=user["username"])
    return {"access_token": token, "token_type": "bearer"}

@router.post("/generate-secret", response_model=GenerateSecretOut)
async def generate_secret(current_user=Depends(get_current_user)):
    import secrets
    token = secrets.token_hex(24)
    await db.users.update_one({"_id": current_user["_id"]}, {"$set": {"secret_token": token}})
    return {"secret_token": token}


@router.get("/get-secret", response_model=GenerateSecretOut)
async def get_secret(current_user=Depends(get_current_user)):
    user = await db.users.find_one({"_id": current_user["_id"]}, {"secret_token": 1})
    return {"secret_token": user.get("secret_token")}

