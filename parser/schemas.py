from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
class FileResponse(BaseModel):
    id:int
    filename: str
    date: str
    content_type: str
    file_path: str

class FileResponsee(BaseModel):
    id: int
    filename: str
    file_path: str

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    apartment_id: Optional[int] = None  
    name: str
    phone: str
    telegram_username: Optional[str] = None  # ✅ NEW FIELD
    client_wishes: Optional[str] = None
    search_time: Optional[str] = None
    residents: Optional[str] = None
    budget: Optional[str] = None  # ✅ Store budget
    district: Optional[str] = None  # ✅ Store "Район"
    rooms: Optional[str] = None  # ✅ Store "Кількість кімнат"
    area: Optional[str] = None  # ✅ Store "Площа (м²)"
    message: Optional[str] = None
    team_leader_id: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    name: str
    phone: str
    ed_status: Optional[str] = None  # Changed to Optional

    apartment_id: Optional[int] =  None   # Make this field optional

    class Config:
        from_attributes = True

class FileApartmentBase(BaseModel):
    filename: str
    date: Optional[str] = None
    content_type: str
    file_path: str
    apartment_id: int

    class Config:
        from_attributes = True  # Enable SQLAlchemy to Pydantic model conversion


class FileApartmentCreate(FileApartmentBase):
    pass  # Use this schema for creation requests

class FileApartmentResponse(BaseModel):
    id: int
    filename: str
    date: Optional[str] = None
    content_type: str
    file_path: str
    apartment_id: int

    class Config:
        from_attributes = True



class ImageOrderUpdate(BaseModel):
    image_id: int
    new_order: int

    class Config:
        from_attributes = True

class TemplateRequest(BaseModel):
    name: str
    template_text: str
    type: str

    class Config:
        from_attributes = True

class RieltorBase(BaseModel):
    username: str

class RieltorCreate(BaseModel):
    username: str
    password: str

class RieltorSchema(BaseModel):
    id: int
    username: str
    profile_picture1: str  # First photo URL
    profile_picture2: str  # Second photo URL

    class Config:
        from_attributes = True  # This ensures compatibility with SQLAlchemy ORM objects





class LoginRequest(BaseModel):
    username: str
    password: str

class ApartmentResponse(BaseModel):
    id: int
    type_deal: Optional[str] = None
    type_object: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    location_date: Optional[str] = None
    description: Optional[str] = None
    features: Optional[str] = None
    owner: Optional[str] = None
    square: Optional[str] = None
    room: Optional[str] = None
    residential_complex: Optional[str] = None
    floor: Optional[str] = None
    superficiality: Optional[str] = None
    classs: Optional[str] = None
    url: Optional[str] = None
    user: Optional[str] = None
    id_olx: Optional[str] = None
    phone: Optional[str] = None  # Already optional
    ad_status: Optional[str] = None  # Already optional
    title_fix: Optional[str] = None
    price_fix: Optional[str] = None
    location_date_fix: Optional[str] = None
    description_fix: Optional[str] = None
    features_fix: Optional[str] = None
    owner_fix: Optional[str] = None
    square_fix: Optional[str] = None
    room_fix: Optional[str] = None
    residential_complex_fix: Optional[str] = None
    floor_fix: Optional[str] = None
    superficiality_fix: Optional[str] = None
    classs_fix: Optional[str] = None
    url_fix: Optional[str] = None
    user_fix: Optional[str] = None
    phone_fix: Optional[str] = None
    last_contact_date: Optional[datetime] = None
    next_contact_date: Optional[datetime] = None
    lease_end_date: Optional[datetime] = None
    rieltor_id: Optional[int] = None
    files: List[FileResponse] = []
    rieltor: Optional[RieltorSchema] = None  # Include the realtor schema

    class Config:
        from_attributes = True  # Use this to ensure compatibility with `from_orm()`

class ApartmentResponsee(BaseModel):
    id: int
    title: Optional[str]
    files: List[FileResponsee] = []

    class Config:
        from_attributes = True

class RieltorResponse(BaseModel):
    id: int
    username: str
    profile_picture1: Optional[str] = None
    profile_picture2: Optional[str] = None
    quote: Optional[str] = None
    apartments: List[ApartmentResponse] = []  # Default to an empty list

    class Config:
        from_attributes = True

class RieltorResponsee(BaseModel):
    id: int
    username: str
    name: Optional[str]
    profile_picture1: Optional[str]
    profile_picture2: Optional[str]
    apartments: Optional[List[ApartmentResponsee]] = None  # Avoid cyclic reference

    class Config:
        from_attributes = True


class RieltorCreate(BaseModel):
    username: str
    password: str
    name: Optional[str] = None
    type: Optional[str] = "realtor"  # Defaults to "realtor" unless specified

    class Config:
        from_attributes = True


class RieltorSchema(BaseModel):
    id: int
    username: str
    name: Optional[str]
    type: str  # "team_leader" or "realtor"

    class Config:
        from_attributes = True

class AssignTeamLeaderRequest(BaseModel):
    realtor_id: int
    team_leader_id: int

class TeamLeaderCreate(BaseModel):
    username: str
    password: str
    name: str  