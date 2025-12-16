from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from datetime import date, datetime
from enum import Enum

class TimeSlot(str, Enum):
    SLOT_A = "一二节课（08:30-10:00）"
    SLOT_B = "三四节课（10:20-11:50）"
    SLOT_C = "中午（12:00-13:50）"
    SLOT_D = "五六节课（14:00-15:30）"
    SLOT_E = "七八节课（15:40-17:10）"
    SLOT_F = "晚上（18:00-21:50）"

class BookingStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class BookingType(str, Enum):
    STUDENT = "student"
    COURSE = "course"

class Room(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    capacity: int
    features: str
    bookings: List["Booking"] = Relationship(back_populates="room")

class Booking(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    student_id: str      
    student_name: str    
    student_email: Optional[str] = None 
    instructor_name: Optional[str] = None 
    
    room_id: int = Field(foreign_key="room.id")
    booking_date: date
    slot: TimeSlot
    purpose: str
    
    status: BookingStatus = Field(default=BookingStatus.PENDING)
    booking_type: BookingType = Field(default=BookingType.STUDENT)
    created_at: datetime = Field(default_factory=datetime.now)
    admin_comment: Optional[str] = None
    
    room: Optional[Room] = Relationship(back_populates="bookings")