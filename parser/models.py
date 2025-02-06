from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from parser.database import Base
from sqlalchemy.orm import relationship
class Apartment(Base):
    __tablename__ = "apartments"

    id = Column(Integer, primary_key=True, index=True)
    type_deal = Column(String, index=True)
    type_object = Column(String, index=True)
    title = Column(String, index=True)
    price = Column(String, index=True)
    location_date = Column(String, index=True)
    description = Column(String)
    features = Column(String)
    owner = Column(String, index=True)
    square = Column(String, index=True)
    room = Column(String, index=True)
    residential_complex = Column(String, index=True)
    floor = Column(String, index=True)
    superficiality = Column(String, index=True)
    classs = Column(String, index=True)
    url = Column(String, unique=True, index=True)
    ad_status = Column(String, index=True)
    on_map = Column(String, unique=True, index=True)
    user = Column(String, index=True)
    phone = Column(String, index=True)
    id_olx = Column(String, index=True)
    comment = Column(String, index=True)



    title_fix = Column(String, index=True)
    price_fix = Column(String, index=True)
    location_date_fix = Column(String, index=True)
    features_fix = Column(String)
    owner_fix = Column(String, index=True)
    square_fix = Column(String, index=True)
    room_fix = Column(String, index=True)
    residential_complex_fix = Column(String, index=True)
    floor_fix = Column(String, index=True)
    superficiality_fix = Column(String, index=True)
    classs_fix = Column(String, index=True)
    url_fix = Column(String, unique=True, index=True)
    user_fix = Column(String, index=True)
    phone_fix = Column(String, index=True)
    is_sending = Column(Boolean, default=False, index=True)  # Transient field

    last_contact_date = Column(DateTime, index=True)
    next_contact_date = Column(DateTime, index=True)
    lease_end_date = Column(DateTime, index=True)
    last_posted_at = Column(DateTime, nullable=True)
    sent_to_sent_channel = Column(Boolean, default=False)
    last_posted_channel_id = Column(String, nullable=True)  # To track the last channel the ad was sent to

    requires_verification = Column(Boolean, default=False)  # Flag for stop words
    is_blacklisted = Column(Boolean, default=False)  # Blacklist flag
    orders = relationship("Order", back_populates="apartment")
    files = relationship("File_apartment", back_populates="apartment_aerial", order_by='File_apartment.order',     lazy="selectin"  ) 
    rieltor_id = Column(Integer, ForeignKey("rieltors.id"), nullable=True)  # Link to a Rieltor
    rieltor = relationship("Rieltor", back_populates="apartments")




class File_apartment(Base):
    __tablename__ = "file_apartment"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    date = Column(String(30), index=True)
    content_type = Column(String(10), nullable=False)
    file_path = Column(String(255), nullable=False)
    order = Column(Integer, nullable=False, default=0)  # New order field
    apartment_id = Column(Integer, ForeignKey("apartments.id"))  # Fixed typo in ForeignKey
    apartment_aerial = relationship("Apartment", back_populates="files")  # Match with updated relationship


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    phone = Column(String, index=True)
    telegram_username = Column(String, index=True)  # ✅ NEW FIELD for @username
    email_adres = Column(String, index=True)
    ed_status = Column(String, index=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id"))  
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  
    client_wishes = Column(String, index=True)
    search_time = Column(String, index=True)
    residents = Column(String, index=True)
    budget = Column(String, index=True)  # ✅ New field to store budget input
    district = Column(String, index=True)  # ✅ Store "Район"
    rooms = Column(String, index=True)  # ✅ Store "Кількість кімнат"
    area = Column(String, index=True)  # ✅ Store "Площа (м²)"
    
    team_leader_id = Column(Integer, ForeignKey("teamleed.id"), nullable=True)  
    team_leader = relationship("TeamLeed", back_populates="orders")  
    apartment = relationship("Apartment", back_populates="orders")


class Rieltor(Base):
    __tablename__ = "rieltors"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    type = Column(String, nullable=False, default="realtor")  # Add a default type for realtors
    profile_picture1 = Column(String, nullable=True)
    profile_picture2 = Column(String, nullable=True)
    quote = Column(String, nullable=True) 

    # Foreign key to Team Leader
    team_leader_id = Column(Integer, ForeignKey("teamleed.id"), nullable=True)

    # Relationships
    team_leader = relationship(
        "TeamLeed",
        back_populates="realtors"
    )

    # Relationship with Apartment
    apartments = relationship(
        "Apartment",
        back_populates="rieltor",
        lazy="selectin"  # Can also use lazy="joined" for tighter integration

    )
class TeamLeed(Base):
    __tablename__ = "teamleed"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String, nullable=False)
    name = Column(String, nullable=True)
    type = Column(String, nullable=False, default="team_leader")  # 'team_leader' or 'realtor'
    orders = relationship("Order", back_populates="team_leader")  # Correct relationship with Order


    # Relationship with Realtors
    # Relationships
    realtors = relationship(
        "Rieltor",
        back_populates="team_leader"
    )


class Template(Base):
    __tablename__ = 'templates'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    template_text = Column(Text, nullable=False)
    type = Column(String, nullable=False)  # Can be 'telegram_bot' or 'telegram_channel'

class TelegramChannel(Base):
    __tablename__ = "telegram_channels"
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)
    type_object = Column(String, nullable=False)
    type_deal = Column(String, nullable=False)  
    channel_id = Column(String, nullable=False)
    price_from = Column(Integer, index=True)  
    price_to = Column(Integer, index=True)    
    location_type = Column(String, index=True)


class SubscribedChat(Base):
    __tablename__ = "subscribed_chats"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(String, unique=True, nullable=False)
    
class TrapBlacklist(Base):
    __tablename__ = "trap_blacklist"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, unique=True, nullable=False)  # Blacklist trap words

class StopWord(Base):
    __tablename__ = "stop_words"

    id = Column(Integer, primary_key=True, index=True)
    word = Column(String, unique=True, nullable=False)  # Words that trigger verification
